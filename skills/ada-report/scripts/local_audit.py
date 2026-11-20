#!/usr/bin/env python3
"""Local mode for ada_report.py: run the accessibility audit on this computer.

`ada_report.py audit URL --local` uses this module. It opens the page in Chromium on the
auditor's own computer and connection, runs the same axe-core version and rule set as the
hosted audit, and scores the result the same way, so the saved JSON and the PDF have the
same shape as a hosted audit. A `run` block inside the result says it was a local run and
records the browser, the axe-core file and the network class; the SHA-256 fingerprint
covers it, so a local run cannot later pass as a hosted one.

What it never does: change the browser's identity, use a proxy, or try to get past a bot
check. If the site turns this computer away too, the run stops and says so.

Privacy: no IP address, hostname or user name is recorded. The network is described only
by its class (for example "private address behind a router"), and the machine by the label
the auditor chooses to type (--machine-label), if any.

Needs `pip install playwright` and `python3 -m playwright install chromium`, plus internet
access to the page and to cdnjs.cloudflare.com (for axe-core). No API key is used.
"""

from __future__ import annotations

import hashlib
import ipaddress
import platform
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

AXE_VERSION = "4.10.3"
AXE_URL = f"https://cdnjs.cloudflare.com/ajax/libs/axe-core/{AXE_VERSION}/axe.min.js"
# The same rule set as the hosted audit.
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]
SETTLE_MS = 2000

WCAG_LEVEL_TAGS = {"wcag2a", "wcag2aa", "wcag21a", "wcag21aa"}
IMPACT_ORDER = ["critical", "serious", "moderate", "minor"]
SEVERITY_BY_IMPACT = {"critical": "critical", "serious": "high", "moderate": "medium", "minor": "low"}

# Page titles of common bot-check / challenge pages. Auditing one of these would describe
# the challenge, not the site, so the run stops instead (and never tries to solve it).
CHALLENGE_TITLES = re.compile(
    r"just a moment|attention required|checking your browser|verify you are human|"
    r"are you a robot|access denied|pardon our interruption|request unsuccessful|"
    r"ddos protection|security check|one more step|captcha",
    re.IGNORECASE,
)


class LocalAuditError(RuntimeError):
    """The page could not be audited from this computer; the message says why."""



# Plain-English fixes. axe's `failureSummary` describes what is wrong ("Element does
# not have an alt attribute"), not what to do, so it is kept as `failure_summary` and
# these are what the report gives as the fix.
FIX_GUIDANCE = {
    # Images
    "image-alt": "Add an alt attribute that says what the image shows or does. Use alt=\"\" only for purely decorative images.",
    "input-image-alt": "Give the image button alt text that names its action, e.g. alt=\"Search\".",
    "area-alt": "Give each <area> in the image map alt text that names where the link goes.",
    "object-alt": "Add a text alternative to the <object>, e.g. an aria-label or fallback text inside it.",
    "svg-img-alt": "Give the SVG an accessible name: add a <title> as its first child, or an aria-label.",
    "role-img-alt": "Give the element with role=\"img\" an aria-label that describes the image.",
    "image-redundant-alt": "Remove the repeated words from the alt text; it shouldn't repeat the caption or link text next to it.",
    # Forms
    "label": "Give the field a visible <label for=\"...\">, or wrap it in a <label>. A placeholder is not a label.",
    "select-name": "Give the <select> a <label for=\"...\"> or an aria-label that says what it chooses.",
    "input-button-name": "Give the button input a value (value=\"Submit\") or an aria-label.",
    "autocomplete-valid": "Use a valid autocomplete token for the field, e.g. autocomplete=\"email\" or \"tel\".",
    "form-field-multiple-labels": "Keep one <label> per field and remove the extras.",
    # Contrast
    "color-contrast": "Increase the contrast between the text and its background to at least 4.5:1 (3:1 for large text). Darken the text or lighten the background.",
    "link-in-text-block": "Make links in body text distinguishable without color: underline them, or give them 3:1 contrast with the surrounding text.",
    # Keyboard
    "tabindex": "Remove tabindex values above 0. Use tabindex=\"0\" and let the DOM order set the tab order.",
    "scrollable-region-focusable": "Make the scrollable area reachable by keyboard: add tabindex=\"0\" or put a focusable element inside it.",
    "bypass": "Add a \"Skip to main content\" link as the first focusable element, or wrap the page content in <main>.",
    "skip-link": "Point the skip link at an element that exists, e.g. href=\"#main\" with id=\"main\" on the content.",
    "nested-interactive": "Don't put a link or button inside another link or button. Split them into separate elements.",
    "focus-order-semantics": "Give focusable elements a role that matches what they do, e.g. use <button> for actions.",
    # ARIA
    "aria-allowed-attr": "Remove ARIA attributes that aren't allowed on this element's role.",
    "aria-hidden-body": "Remove aria-hidden=\"true\" from <body>; it hides the whole page from screen readers.",
    "aria-hidden-focus": "Remove focusable elements from inside aria-hidden content, or add tabindex=\"-1\" to them.",
    "aria-input-field-name": "Give the ARIA input an accessible name with aria-label or aria-labelledby.",
    "aria-toggle-field-name": "Give the toggle an accessible name with aria-label or aria-labelledby.",
    "aria-required-attr": "Add the ARIA attributes this role requires, e.g. aria-checked on role=\"checkbox\".",
    "aria-required-children": "Add the child roles this element needs, e.g. role=\"listitem\" inside role=\"list\".",
    "aria-required-parent": "Place the element inside the parent role it needs, e.g. role=\"tab\" inside role=\"tablist\".",
    "aria-roles": "Replace the invalid role with a valid ARIA role, or remove it.",
    "aria-valid-attr": "Fix or remove the misspelled or invalid ARIA attribute.",
    "aria-valid-attr-value": "Give the ARIA attribute a valid value, e.g. aria-expanded=\"true\" or \"false\".",
    "aria-command-name": "Give the element an accessible name with inner text, aria-label, or aria-labelledby.",
    "aria-dialog-name": "Give the dialog an accessible name with aria-label or aria-labelledby.",
    "aria-prohibited-attr": "Remove aria-label/aria-labelledby from this element; its role doesn't allow a name.",
    # Structure
    "document-title": "Add a <title> in <head> that describes the page.",
    "html-has-lang": "Add a lang attribute to <html>, e.g. <html lang=\"en\">.",
    "html-lang-valid": "Use a valid language code in <html lang>, e.g. \"en\" or \"en-US\".",
    "html-xml-lang-mismatch": "Make the lang and xml:lang attributes on <html> use the same language.",
    "valid-lang": "Use a valid language code in the lang attribute.",
    "heading-order": "Don't skip heading levels: an <h2> should follow an <h1>, an <h3> an <h2>. Change the tag, not just the font size.",
    "page-has-heading-one": "Add one <h1> that names the page's main topic.",
    "landmark-one-main": "Wrap the page's main content in a single <main> element.",
    "landmark-unique": "Give repeated landmarks (e.g. two <nav>) distinct aria-labels, like \"Main\" and \"Footer\".",
    "landmark-no-duplicate-main": "Keep one <main> element per page.",
    "landmark-complementary-is-top-level": "Move the <aside> out of other landmarks so it sits at the top level.",
    "landmark-banner-is-top-level": "Move the <header> banner out of other landmarks so it sits at the top level.",
    "landmark-contentinfo-is-top-level": "Move the <footer> out of other landmarks so it sits at the top level.",
    "region": "Put all visible content inside a landmark: <header>, <nav>, <main>, or <footer>.",
    "empty-heading": "Give the heading text, or remove the empty heading tag.",
    "list": "Only put <li>, <script> or <template> directly inside <ul>/<ol>.",
    "listitem": "Put each <li> inside a <ul> or <ol>.",
    "definition-list": "Only put <dt>/<dd> groups directly inside <dl>.",
    "dlitem": "Put <dt> and <dd> inside a <dl>.",
    "frame-title": "Add a title attribute to the iframe that says what it contains, e.g. title=\"Map of our office\".",
    "frame-title-unique": "Give each iframe a distinct title.",
    "duplicate-id-active": "Give each focusable element a unique id.",
    "duplicate-id-aria": "Give each element referenced by ARIA or a label a unique id.",
    "duplicate-id": "Give each element a unique id.",
    # Links / buttons
    "link-name": "Give the link text that says where it goes. For an icon link, add an aria-label.",
    "button-name": "Give the button visible text, or an aria-label for an icon-only button.",
    "identical-links-same-purpose": "Links with the same text should go to the same place, or say how they differ.",
    # Tables
    "empty-table-header": "Give the empty <th> text, or make it a <td> if it isn't a header.",
    "td-headers-attr": "Point each cell's headers attribute at <th> ids in the same table.",
    "th-has-data-cells": "Make sure each <th> labels data cells, or change it to a <td>.",
    "table-fake-caption": "Replace the first-row \"caption\" cell with a real <caption> element.",
    "scope-attr-valid": "Use scope=\"row\" or scope=\"col\", and only on <th>.",
    "table-duplicate-name": "Make the table's <caption> and summary say different things.",
    # Media
    "video-caption": "Add captions to the video with a <track kind=\"captions\">.",
    "audio-caption": "Provide captions or a transcript for the audio.",
    "no-autoplay-audio": "Don't autoplay audio longer than 3 seconds, or give users a control to stop it.",
    "blink": "Remove <blink>; blinking content can't be paused.",
    "marquee": "Remove <marquee>; moving content can't be paused.",
    # Viewport
    "meta-viewport": "Allow zoom: remove user-scalable=no and any maximum-scale below 2 from the viewport meta tag.",
    "meta-viewport-large": "Allow users to zoom to at least 500%: raise or remove maximum-scale.",
    "meta-refresh": "Remove the automatic <meta http-equiv=\"refresh\"> redirect, or give users control of it.",
}

# What to check by hand when axe can't decide (`incomplete`).
REVIEW_GUIDANCE = {
    "color-contrast": "Contrast couldn't be measured automatically, usually because the text sits on a background image, gradient, or an overlapping element. Check it with a contrast checker: 4.5:1 for normal text, 3:1 for large text.",
    "color-contrast-enhanced": "Contrast couldn't be measured automatically. Check it with a contrast checker.",
    "link-in-text-block": "Check that links in body text can be told apart from the text around them without relying on color.",
    "video-caption": "Check that the video has accurate captions.",
    "audio-caption": "Check that the audio has captions or a transcript.",
    "frame-tested": "The iframe's content couldn't be tested (usually because it's on another domain). Audit the embedded page's URL separately.",
    "aria-valid-attr-value": "Check that the ARIA attribute points at an element that exists and holds a valid value.",
    "aria-allowed-role": "Check that the role suits the element.",
    "td-headers-attr": "Check that each data cell is associated with the right header cells.",
    "th-has-data-cells": "Check that each table header labels data cells.",
    "p-as-heading": "Check whether the bold or large paragraph is really a heading; if so, use a heading tag.",
    "label-content-name-mismatch": "Check that the accessible name contains the visible label text, so voice-control users can say what they see.",
    "scrollable-region-focusable": "Check that keyboard users can reach and scroll the scrollable area.",
    "select-name": "Check that the dropdown has a label that says what it chooses.",
    "duplicate-id-aria": "Check that ids referenced by ARIA or labels are unique.",
    "nested-interactive": "Check that no link or button is nested inside another.",
    "target-size": "Check that touch targets are at least 24x24 CSS pixels.",
}



# ---------------------------------------------------------------------------
# Where the run came from (no personal data)
# ---------------------------------------------------------------------------

def address_class(addr: str) -> str:
    """Describe an address by its class only. The address itself is never kept."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return "unknown"
    if ip.is_loopback:
        return "loopback (no outside network)"
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return "shared carrier address (carrier-grade NAT, common on mobile and some ISPs)"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_private:
        return "private address behind a router (home or office network)"
    return "public address assigned directly to this computer"


def network_class(host: str, port: int = 443) -> dict[str, Any]:
    """The class of the local address this computer uses to reach `host`.

    Connecting a UDP socket only picks a route; it sends no packets. The address is read,
    classified, and dropped: nothing but its class and IP version is returned.
    """
    try:
        family, _, _, _, sockaddr = socket.getaddrinfo(host, port, proto=socket.IPPROTO_UDP)[0]
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.connect(sockaddr)
            local = s.getsockname()[0]
    except OSError:
        return {"ip_version": None, "local_address_class": "unknown"}
    return {"ip_version": ipaddress.ip_address(local).version,
            "local_address_class": address_class(local)}


def machine_info(label: str = "") -> dict[str, Any]:
    return {"label": label.strip(), "os": platform.system() or "unknown",
            "arch": platform.machine() or "unknown"}


# ---------------------------------------------------------------------------
# axe-core
# ---------------------------------------------------------------------------

def fetch_axe() -> tuple[str, str]:
    """axe-core source and its SHA-256 (recorded, so the exact engine file is known)."""
    req = urllib.request.Request(AXE_URL, headers={"User-Agent": "ada-report-local"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw: bytes = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        raise LocalAuditError(f"could not download axe-core from {AXE_URL} ({exc}). Check "
                              "the internet connection.") from exc
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Scoring: the same rules as the hosted audit
# ---------------------------------------------------------------------------

def _is_wcag(rule: dict[str, Any]) -> bool:
    return any(t in WCAG_LEVEL_TAGS for t in rule.get("tags", []))


def _impact(rule: dict[str, Any]) -> str:
    impact = rule.get("impact") or "minor"
    return impact if impact in IMPACT_ORDER else "minor"


def _node_messages(node: dict[str, Any]) -> list[str]:
    return [c["message"] for b in ("any", "all", "none") for c in (node.get(b) or [])
            if c.get("message")]


def _contrast_fix(node: dict[str, Any]) -> str | None:
    for check in node.get("any", []) or []:
        data = check.get("data")
        if not isinstance(data, dict) or not data.get("contrastRatio"):
            continue
        need = str(data.get("expectedContrastRatio", "4.5:1"))
        return (f"Text contrast is {data['contrastRatio']}:1 ({data.get('fgColor')} on "
                f"{data.get('bgColor')}); it needs at least {need}. Darken the text or lighten "
                "the background until it passes.")
    return None


def _fix_for(rule_id: str, help_text: str, help_url: str,
             node: dict[str, Any] | None = None) -> str:
    if rule_id == "color-contrast" and node:
        specific = _contrast_fix(node)
        if specific:
            return specific
    if rule_id in FIX_GUIDANCE:
        return FIX_GUIDANCE[rule_id]
    base = help_text.rstrip(".") if help_text else "Fix this issue"
    return f"{base}. See {help_url} for how to fix it." if help_url else f"{base}."


def _rule_detail(v: dict[str, Any]) -> dict[str, Any]:
    rid, help_text, help_url = v["id"], v.get("help", ""), v.get("helpUrl", "")
    nodes = v.get("nodes", [])
    return {
        "rule_id": rid, "impact": _impact(v),
        "type": "wcag" if _is_wcag(v) else "best_practice",
        "description": v.get("description", ""), "help": help_text, "help_url": help_url,
        "wcag_tags": [t for t in v.get("tags", []) if t.startswith("wcag")],
        "fix": _fix_for(rid, help_text, help_url),
        "affected_elements": min(len(nodes), 10),
        "element_samples": [
            {"html": n.get("html", "")[:200], "target": n.get("target", []),
             "fix_suggestion": _fix_for(rid, help_text, help_url, n),
             "failure_summary": (n.get("failureSummary") or "")[:300]}
            for n in nodes[:3]],
    }


def _review_item(v: dict[str, Any]) -> dict[str, Any]:
    rid, help_text = v["id"], v.get("help", "")
    nodes = v.get("nodes", [])
    default = (f"Automated testing couldn't decide this one. Check by hand: "
               f"{help_text.rstrip('.')}." if help_text
               else "Automated testing couldn't decide this one. Check it by hand.")
    return {
        "rule_id": rid, "type": "wcag" if _is_wcag(v) else "best_practice",
        "impact": v.get("impact"), "description": v.get("description", ""),
        "help": help_text, "help_url": v.get("helpUrl", ""),
        "wcag_tags": [t for t in v.get("tags", []) if t.startswith("wcag")],
        "what_to_check": REVIEW_GUIDANCE.get(rid, default),
        "affected_elements": min(len(nodes), 10),
        "element_samples": [{"html": n.get("html", "")[:200], "target": n.get("target", []),
                             "reason": "; ".join(_node_messages(n))[:300]} for n in nodes[:3]],
    }


def grade_for(score: float) -> str:
    for floor, grade in ((95, "A+"), (90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if score >= floor:
            return grade
    return "F"


def build_report(axe_results: dict[str, Any], final_url: str, status_code: int) -> dict[str, Any]:
    """Score raw axe output the way the hosted audit does (WCAG A/AA rules only;
    best-practice findings and needs-review items never touch the score)."""
    violations = axe_results.get("violations", [])
    passes = axe_results.get("passes", [])
    incomplete = axe_results.get("incomplete", [])
    wcag_v = [v for v in violations if _is_wcag(v)]
    bp_v = [v for v in violations if not _is_wcag(v)]
    wcag_p = [p for p in passes if _is_wcag(p)]

    details = sorted((_rule_detail(v) for v in wcag_v), key=lambda d: IMPACT_ORDER.index(d["impact"]))
    best = sorted((_rule_detail(v) for v in bp_v), key=lambda d: IMPACT_ORDER.index(d["impact"]))

    decided = len(wcag_v) + len(wcag_p)
    if decided == 0:
        score = 100.0
    else:
        deductions = 0.0
        for v in wcag_v:
            n = min(len(v.get("nodes", [])), 5)
            deductions += {"critical": 8 + n * 1.5, "serious": 5 + n * 1.0,
                           "moderate": 3 + n * 0.5}.get(_impact(v), 1)
        score = max(0.0, min(100.0, len(wcag_p) / decided * 100 - deductions))
    score = round(score, 1)

    def _priority(d: dict[str, Any]) -> dict[str, Any]:
        return {"severity": SEVERITY_BY_IMPACT[d["impact"]] if d["type"] == "wcag" else "low",
                "impact": d["impact"], "type": d["type"], "rule_id": d["rule_id"],
                "issue": d["help"], "fix": d["fix"], "help_url": d["help_url"],
                "affected_elements": d["affected_elements"]}

    return {
        "url": final_url, "score": score, "grade": grade_for(score),
        "standard": "WCAG 2.1 AA", "response_code": status_code,
        "summary": {"total_rules_checked": len(violations) + len(passes) + len(incomplete),
                    "violations": len(wcag_v), "passes": len(wcag_p),
                    "incomplete": len(incomplete), "best_practice_issues": len(bp_v)},
        "violations": details, "best_practices": best,
        "needs_review": [_review_item(v) for v in incomplete],
        "priorities": [_priority(d) for d in (details + best)[:10]],
    }


# ---------------------------------------------------------------------------
# The browser run
# ---------------------------------------------------------------------------

REFUSED = ("The site refused this computer too (HTTP {status}). The local run does not try "
           "to get past bot protection. Ask the site owner to allow the audit, or audit a "
           "page that loads without a bot check.")
CHALLENGE = ("The page showed a bot check (\"{title}\") instead of the site. The local run "
             "does not solve or get around bot checks, so there is nothing to audit. Ask the "
             "site owner to allow the audit, or try again later from a network the site "
             "already lets in.")


def status_problem(status: int) -> str | None:
    if status in (401, 403, 429, 503):
        return REFUSED.format(status=status)
    if status in (404, 410):
        return f"The page was not found (HTTP {status})."
    if status >= 400:
        return f"The page returned HTTP {status}."
    return None


def challenge_problem(title: str) -> str | None:
    t = (title or "").strip()
    return CHALLENGE.format(title=t[:80]) if t and CHALLENGE_TITLES.search(t) else None


def _nav_problem(exc: Exception) -> str:
    msg = str(exc)
    if "ERR_NAME_NOT_RESOLVED" in msg:
        return "The domain name could not be resolved (DNS lookup failed)."
    if "ERR_CERT" in msg or "ERR_SSL" in msg:
        return "The site's TLS/SSL certificate is invalid, so the page could not be loaded securely."
    if any(m in msg for m in ("ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED",
                              "ERR_EMPTY_RESPONSE", "ERR_HTTP2_PROTOCOL_ERROR")):
        return ("The site closed the connection from this computer too. The local run does "
                "not try to get past bot protection; ask the site owner to allow the audit.")
    if "imeout" in msg:
        return "The page did not finish loading in time."
    return f"The page could not be loaded ({msg.splitlines()[0][:200] if msg else 'no detail'})."


def run_local(url: str, timeout: int = 30, headed: bool = False,
              machine_label: str = "", tool_version: str = "") -> dict[str, Any]:
    """Audit `url` in Chromium on this computer. Returns a result shaped like the hosted
    audit's, plus a `run` block. Raises LocalAuditError when the page can't be audited."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LocalAuditError("--local needs Playwright: pip install playwright && "
                              "python3 -m playwright install chromium") from exc

    host = urllib.parse.urlparse(url).hostname or ""
    if not host:
        raise LocalAuditError(f"not a web address: {url}")
    axe_src, axe_sha = fetch_axe()
    network = network_class(host)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=not headed)
        except PlaywrightError as exc:
            raise LocalAuditError("could not start Chromium. Run: python3 -m playwright "
                                  f"install chromium ({str(exc).splitlines()[0]})") from exc
        try:
            # bypass_csp lets the injected axe-core run on pages whose CSP limits scripts
            # (the hosted audit does the same). The browser identity is left as it is.
            context = browser.new_context(bypass_csp=True)
            page = context.new_page()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except PlaywrightError as exc:
                raise LocalAuditError(_nav_problem(exc)) from exc
            if resp is None:
                raise LocalAuditError("The page could not be loaded.")
            problem = status_problem(resp.status)
            if problem:
                raise LocalAuditError(problem)
            ctype = (resp.headers.get("content-type") or "").lower()
            if ctype and "html" not in ctype:
                raise LocalAuditError(f"The URL returned {ctype.split(';')[0]}, not an HTML page.")
            page.wait_for_timeout(SETTLE_MS)
            problem = challenge_problem(page.title())
            if problem:
                raise LocalAuditError(problem)
            try:
                page.add_script_tag(content=axe_src)
                page.wait_for_function("typeof axe !== 'undefined'", timeout=10000)
                axe_results = page.evaluate(
                    "(tags) => axe.run(document, {runOnly: {type: 'tag', values: tags},"
                    " resultTypes: ['violations', 'passes', 'incomplete']}).then(r => ({"
                    "violations: r.violations, passes: r.passes, incomplete: r.incomplete}))",
                    AXE_TAGS)
            except PlaywrightError as exc:
                raise LocalAuditError(f"axe-core could not run on the page ({str(exc).splitlines()[0]}).") from exc
            user_agent = page.evaluate("navigator.userAgent")
            final_url, status = page.url, resp.status
            browser_version = browser.version
        finally:
            browser.close()

    result = build_report(axe_results, final_url, status)
    result["run"] = {
        "location": "local",
        "tool_version": tool_version,
        "machine": machine_info(machine_label),
        "network": network,
        "browser": {"engine": "Chromium (Playwright)", "version": browser_version,
                    "headless": not headed, "user_agent": user_agent,
                    "identity": "unchanged: no user-agent override, no proxy, no bot-check solving"},
        "axe_core": {"version": AXE_VERSION, "source": AXE_URL, "sha256": axe_sha},
    }
    return result
