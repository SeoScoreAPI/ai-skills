#!/usr/bin/env python3
"""ADA / WCAG 2.1 AA accessibility audits as dated, readable PDF reports.

Wraps the SEO Score API accessibility endpoint (https://seoscoreapi.com). Three commands:

    ada_report.py audit https://example.com [more URLs...] [--out audits/]
        Runs the audit, saves the raw result as JSON with the UTC time and a SHA-256
        fingerprint, and writes a PDF next to it.

    ada_report.py pdf audits/example.com-20260929T2150Z.json [--out report.pdf]
        Re-renders the PDF for a saved audit.

    ada_report.py compare before.json after.json [--out remediation.pdf]
        Before/after remediation report: resolved, still open, and new issues.

Needs SEO_SCORE_API_KEY (free key at https://seoscoreapi.com) and `pip install fpdf2`.
Works the same from Claude, ChatGPT, Gemini, or a plain terminal: it is plain Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
API_BASE = os.environ.get("SEO_SCORE_API_BASE", "https://seoscoreapi.com").rstrip("/")
ENDPOINT = "/audit/accessibility"

# WCAG 2.1 success criteria (A / AA) that automated checks can map to.
WCAG_SC: dict[str, tuple[str, str]] = {
    "1.1.1": ("Non-text Content", "A"), "1.2.1": ("Audio-only and Video-only", "A"),
    "1.2.2": ("Captions (Prerecorded)", "A"), "1.2.3": ("Audio Description or Media Alternative", "A"),
    "1.2.5": ("Audio Description (Prerecorded)", "AA"), "1.3.1": ("Info and Relationships", "A"),
    "1.3.2": ("Meaningful Sequence", "A"), "1.3.3": ("Sensory Characteristics", "A"),
    "1.3.4": ("Orientation", "AA"), "1.3.5": ("Identify Input Purpose", "AA"),
    "1.4.1": ("Use of Color", "A"), "1.4.2": ("Audio Control", "A"),
    "1.4.3": ("Contrast (Minimum)", "AA"), "1.4.4": ("Resize Text", "AA"),
    "1.4.5": ("Images of Text", "AA"), "1.4.10": ("Reflow", "AA"),
    "1.4.11": ("Non-text Contrast", "AA"), "1.4.12": ("Text Spacing", "AA"),
    "1.4.13": ("Content on Hover or Focus", "AA"), "2.1.1": ("Keyboard", "A"),
    "2.1.2": ("No Keyboard Trap", "A"), "2.1.4": ("Character Key Shortcuts", "A"),
    "2.2.1": ("Timing Adjustable", "A"), "2.2.2": ("Pause, Stop, Hide", "A"),
    "2.3.1": ("Three Flashes or Below Threshold", "A"), "2.4.1": ("Bypass Blocks", "A"),
    "2.4.2": ("Page Titled", "A"), "2.4.3": ("Focus Order", "A"),
    "2.4.4": ("Link Purpose (In Context)", "A"), "2.4.5": ("Multiple Ways", "AA"),
    "2.4.6": ("Headings and Labels", "AA"), "2.4.7": ("Focus Visible", "AA"),
    "2.5.1": ("Pointer Gestures", "A"), "2.5.2": ("Pointer Cancellation", "A"),
    "2.5.3": ("Label in Name", "A"), "2.5.4": ("Motion Actuation", "A"),
    "3.1.1": ("Language of Page", "A"), "3.1.2": ("Language of Parts", "AA"),
    "3.2.1": ("On Focus", "A"), "3.2.2": ("On Input", "A"),
    "3.2.3": ("Consistent Navigation", "AA"), "3.2.4": ("Consistent Identification", "AA"),
    "3.3.1": ("Error Identification", "A"), "3.3.2": ("Labels or Instructions", "A"),
    "3.3.3": ("Error Suggestion", "AA"), "3.3.4": ("Error Prevention (Legal, Financial, Data)", "AA"),
    "4.1.1": ("Parsing", "A"), "4.1.2": ("Name, Role, Value", "A"),
    "4.1.3": ("Status Messages", "AA"),
}

LIMITS = (
    "This report lists what automated accessibility testing (the axe-core rule engine, run "
    "through SEO Score API in a real browser) found on the page(s) named above at the time "
    "shown. Automated tools detect a subset of WCAG 2.1 AA issues, commonly estimated at a "
    "third to a half; many criteria (for example meaningful alt text, keyboard-only use of "
    "complex widgets, captions quality) need manual review by a person. A clean automated "
    "result is not proof of conformance, and this report is not a legal opinion. Results "
    "reflect the page as served to the testing browser; content behind logins, later "
    "changes, or other pages are not covered."
)


# ---------------------------------------------------------------------------
# API + storage
# ---------------------------------------------------------------------------

def api_key() -> str:
    key = os.environ.get("SEO_SCORE_API_KEY", "").strip()
    if not key:
        sys.exit("SEO_SCORE_API_KEY is not set. Get a free key at https://seoscoreapi.com")
    return key


def run_audit(url: str) -> dict[str, Any]:
    q = urllib.parse.urlencode({"url": url})
    req = urllib.request.Request(f"{API_BASE}{ENDPOINT}?{q}", headers={
        "X-API-Key": api_key(), "User-Agent": f"seoscoreapi-ada-report/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data: dict[str, Any] = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        sys.exit(f"{url}: HTTP {exc.code} {detail}")
    return data


def fingerprint(result: dict[str, Any]) -> str:
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def wrap(url: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "seoscoreapi ada-report", "tool_version": VERSION,
        "requested_url": url, "audited_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "api": f"{API_BASE}{ENDPOINT}", "sha256": fingerprint(result), "result": result,
    }


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    if "result" not in data:  # a raw API response saved by hand
        data = {"requested_url": data.get("url", ""), "audited_at": "", "sha256":
                fingerprint(data), "result": data}
    elif data.get("sha256") and fingerprint(data["result"]) != data["sha256"]:
        print(f"warning: {path} fingerprint does not match its contents (edited?)",
              file=sys.stderr)
    return data


def slug(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc or url
    path = urllib.parse.urlparse(url).path.strip("/").replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", host + ("_" + path if path else ""))[:80]


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def criteria(tags: list[str]) -> list[str]:
    """['wcag2aa', 'wcag143'] -> ['1.4.3']"""
    out = []
    for t in tags or []:
        m = re.fullmatch(r"wcag(\d)(\d)(\d{1,2})", t)
        if m:
            out.append(".".join(m.groups()))
    return out


def sc_label(sc: str) -> str:
    name, level = WCAG_SC.get(sc, ("", ""))
    return f"{sc} {name} ({level})" if name else sc


def targets(v: dict[str, Any]) -> set[str]:
    return {" ".join(s.get("target") or []) for s in v.get("element_samples") or []}


IMPACT_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}


def violations(result: dict[str, Any]) -> list[dict[str, Any]]:
    vs = list(result.get("violations") or [])
    return sorted(vs, key=lambda v: (IMPACT_ORDER.get(v.get("impact", ""), 9),
                                     -int(v.get("affected_elements") or 0)))


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _pdf_class() -> Any:
    try:
        from fpdf import FPDF
    except ImportError:
        sys.exit("Missing dependency: pip install fpdf2")

    class Report(FPDF):  # type: ignore[misc]
        footer_text = ""

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, clean(f"{self.footer_text}   Page {self.page_no()}/{{nb}}"),
                      align="C")
    return Report


def clean(text: Any) -> str:
    s = str(text if text is not None else "")
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"')
         .replace("”", '"').replace("–", "-").replace("—", "-")
         .replace("…", "...").replace(" ", " "))
    return s.encode("latin-1", "replace").decode("latin-1")


class Writer:
    def __init__(self, title: str, footer: str) -> None:
        self.pdf = _pdf_class()(format="Letter")
        self.pdf.footer_text = footer
        self.pdf.alias_nb_pages()
        self.pdf.set_auto_page_break(True, margin=16)
        self.pdf.set_margins(16, 16, 16)
        self.pdf.add_page()
        self.pdf.set_title(clean(title))
        self.pdf.set_creator(f"SEO Score API ada-report {VERSION}")

    @property
    def w(self) -> float:
        return float(self.pdf.w - self.pdf.l_margin - self.pdf.r_margin)

    def h1(self, text: str) -> None:
        self.pdf.set_font("Helvetica", "B", 18)
        self.pdf.set_text_color(15, 23, 42)
        self.pdf.multi_cell(self.w, 9, clean(text), align="L", new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(1)

    def h2(self, text: str) -> None:
        self.pdf.ln(3)
        self.pdf.set_font("Helvetica", "B", 12)
        self.pdf.set_text_color(15, 23, 42)
        self.pdf.multi_cell(self.w, 7, clean(text), align="L", new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_draw_color(200, 200, 200)
        self.pdf.line(self.pdf.l_margin, self.pdf.get_y(), self.pdf.w - self.pdf.r_margin,
                      self.pdf.get_y())
        self.pdf.ln(2)

    def p(self, text: str, size: float = 9.5, bold: bool = False,
          color: tuple[int, int, int] = (30, 30, 30), mono: bool = False) -> None:
        self.pdf.set_font("Courier" if mono else "Helvetica", "B" if bold else "", size)
        self.pdf.set_text_color(*color)
        self.pdf.multi_cell(self.w, size * 0.5, clean(text), align="L", new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(0.8)

    def kv(self, rows: list[tuple[str, str]]) -> None:
        for k, v in rows:
            self.pdf.set_font("Helvetica", "B", 9)
            self.pdf.set_text_color(90, 90, 90)
            self.pdf.cell(42, 5.5, clean(k))
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(20, 20, 20)
            self.pdf.multi_cell(self.w - 42, 5.5, clean(v), align="L", new_x="LMARGIN", new_y="NEXT")

    def table(self, head: list[str], rows: list[list[str]], widths: list[float]) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(20, 20, 20)
        from fpdf.fonts import FontFace

        head_style = FontFace(emphasis="BOLD", fill_color=(241, 245, 249))
        with pdf.table(col_widths=widths, width=sum(widths), line_height=4.8,
                       text_align="LEFT", headings_style=head_style) as t:
            for r in [head] + rows:
                row = t.row()
                for c in r:
                    row.cell(clean(c))
        pdf.ln(2)

    def save(self, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(out))


def when(iso: str) -> str:
    if not iso:
        return "not recorded (raw API response)"
    try:
        return datetime.fromisoformat(iso).strftime("%B %d, %Y at %H:%M UTC")
    except ValueError:
        return iso


def render_audit(data: dict[str, Any], out: Path, prepared_for: str = "") -> Path:
    r = data["result"]
    url = r.get("url") or data.get("requested_url", "")
    summ = r.get("summary") or {}
    vs = violations(r)
    w = Writer(f"Accessibility audit: {url}",
               f"SEO Score API accessibility audit | {url} | {when(data.get('audited_at',''))}"
               f" | SHA-256 {data.get('sha256','')[:16]}...")
    w.h1("Website Accessibility Audit")
    w.p(f"{url}", 11, bold=True, color=(37, 99, 235))
    w.pdf.ln(2)
    rows = [("Audited", when(data.get("audited_at", ""))),
            ("Standard", str(r.get("standard") or "WCAG 2.1 AA")),
            ("Method", "Automated axe-core checks in a real browser (SEO Score API)"),
            ("HTTP status", str(r.get("response_code", ""))),
            ("Fingerprint", f"SHA-256 {data.get('sha256','')}")]
    if prepared_for:
        rows.insert(0, ("Prepared for", prepared_for))
    w.kv(rows)

    w.h2("Summary")
    risk = (r.get("lawsuit_risk") or {})
    w.kv([("Score", f"{r.get('score', '?')}/100 (grade {r.get('grade', '?')})"),
          ("Rules checked", str(summ.get("total_rules_checked", ""))),
          ("Failed", f"{summ.get('violations', len(vs))} rule(s), "
                     f"{sum(int(v.get('affected_elements') or 0) for v in vs)} element(s)"),
          ("Passed", str(summ.get("passes", ""))),
          ("Needs manual review", str(summ.get("incomplete", ""))),
          ("Automated risk flag", f"{risk.get('level', 'n/a')}: {risk.get('summary', '')}")])

    w.h2("Issues found")
    if not vs:
        w.p("No automated WCAG 2.1 AA failures were detected on this page. See the limits "
            "section: automated testing does not cover every criterion.")
    else:
        w.table(["#", "WCAG criterion", "Impact", "Elements", "Issue"],
                [[str(i), ", ".join(sc_label(c) for c in criteria(v.get("wcag_tags")))
                  or "best practice", str(v.get("impact", "")),
                  str(v.get("affected_elements", "")), str(v.get("help", ""))]
                 for i, v in enumerate(vs, 1)],
                [8, 52, 18, 18, w.w - 96])

        w.h2("Details")
        for i, v in enumerate(vs, 1):
            w.p(f"{i}. {v.get('help', '')}", 10.5, bold=True, color=(15, 23, 42))
            scs = criteria(v.get("wcag_tags"))
            w.kv([("WCAG", ", ".join(sc_label(c) for c in scs) or "best practice (not a "
                   "WCAG failure)"),
                  ("Impact", str(v.get("impact", ""))),
                  ("Elements affected", str(v.get("affected_elements", ""))),
                  ("Rule", f"{v.get('rule_id', '')} ({v.get('help_url', '')})")])
            if v.get("description"):
                w.p(v["description"], 9)
            if v.get("fix"):
                w.p(f"Fix: {v['fix']}", 9, bold=True, color=(22, 101, 52))
            for s in (v.get("element_samples") or [])[:5]:
                w.p("Element: " + " ".join(s.get("target") or []), 8, mono=True,
                    color=(71, 85, 105))
                if s.get("html"):
                    w.p(re.sub(r"\s+", " ", s["html"])[:300], 7.5, mono=True,
                        color=(100, 116, 139))
                if s.get("fix_suggestion"):
                    w.p(s["fix_suggestion"], 8.5)
            w.pdf.ln(2)

    bp = r.get("best_practices") or []
    if bp:
        w.h2("Best practices (not WCAG failures)")
        w.p("axe-core best-practice findings. They are not WCAG 2.1 AA requirements and do "
            "not affect the score.", 8.5, color=(71, 85, 105))
        for v in bp:
            w.p(f"- {v.get('help') or v.get('description') or v.get('rule_id')}"
                f" ({v.get('affected_elements', '?')} element(s))", 9)

    review = r.get("needs_review") or []
    if review:
        w.h2("Needs manual review")
        for v in review:
            w.p(f"- {v.get('help') or v.get('description') or v.get('rule_id')}"
                f" ({v.get('affected_elements', '?')} element(s))", 9)

    w.h2("Scope and limits")
    w.p(LIMITS, 8.5, color=(71, 85, 105))
    w.p(f"Raw result preserved in the audit JSON; recomputing SHA-256 over its 'result' "
        f"object (sorted keys, compact) reproduces {data.get('sha256','')}.", 8,
        color=(100, 116, 139))
    w.p("Generated with the open-source ada-report skill: github.com/SeoScoreAPI | "
        "API: seoscoreapi.com", 8, color=(100, 116, 139))
    w.save(out)
    return out


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    b = {v["rule_id"]: v for v in violations(before["result"])}
    a = {v["rule_id"]: v for v in violations(after["result"])}
    resolved = [b[k] for k in b if k not in a]
    new = [a[k] for k in a if k not in b]
    still = []
    for k in b:
        if k in a:
            fixed = targets(b[k]) - targets(a[k])
            still.append({**a[k], "_before": int(b[k].get("affected_elements") or 0),
                          "_fixed_samples": sorted(fixed)})
    return {"resolved": resolved, "still_open": still, "new": new}


def render_compare(before: dict[str, Any], after: dict[str, Any], out: Path,
                   prepared_for: str = "") -> Path:
    url = after["result"].get("url") or after.get("requested_url", "")
    d = diff(before, after)
    w = Writer(f"Remediation report: {url}",
               f"SEO Score API remediation report | {url} | "
               f"before {before.get('sha256','')[:12]} | after {after.get('sha256','')[:12]}")
    w.h1("Accessibility Remediation Report")
    w.p(url, 11, bold=True, color=(37, 99, 235))
    w.pdf.ln(2)
    rows = [("Before", f"{when(before.get('audited_at',''))}  (score "
                       f"{before['result'].get('score','?')}, SHA-256 {before.get('sha256','')[:16]}...)"),
            ("After", f"{when(after.get('audited_at',''))}  (score "
                      f"{after['result'].get('score','?')}, SHA-256 {after.get('sha256','')[:16]}...)"),
            ("Standard", "WCAG 2.1 AA, automated axe-core checks (SEO Score API)")]
    if prepared_for:
        rows.insert(0, ("Prepared for", prepared_for))
    w.kv(rows)

    w.h2("Result")
    w.kv([("Resolved", f"{len(d['resolved'])} issue(s)"),
          ("Still open", f"{len(d['still_open'])} issue(s)"),
          ("New since before", f"{len(d['new'])} issue(s)")])

    def section(title: str, items: list[dict[str, Any]], still: bool = False) -> None:
        w.h2(title)
        if not items:
            w.p("None.")
            return
        rows = []
        for v in items:
            count = str(v.get("affected_elements", ""))
            if still:
                count = f"{v['_before']} -> {v.get('affected_elements', '')}"
            rows.append([", ".join(sc_label(c) for c in criteria(v.get("wcag_tags")))
                         or "best practice", str(v.get("impact", "")), count,
                         str(v.get("help", ""))])
        w.table(["WCAG criterion", "Impact", "Elements", "Issue"], rows,
                [55, 18, 22, w.w - 95])

    section("Resolved", d["resolved"])
    section("Still open", d["still_open"], still=True)
    section("New since the first audit", d["new"])
    w.h2("Scope and limits")
    w.p(LIMITS, 8.5, color=(71, 85, 105))
    w.p("Issues are matched by axe-core rule between the two audits; element counts come "
        "from each audit. Both raw results are preserved in their audit JSON files.", 8,
        color=(100, 116, 139))
    w.save(out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ada_report.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit URL(s): saves JSON + PDF")
    a.add_argument("urls", nargs="*")
    a.add_argument("--file", type=Path, help="text file with one URL per line")
    a.add_argument("--out", type=Path, default=Path("accessibility-audits"))
    a.add_argument("--prepared-for", default="")
    p = sub.add_parser("pdf", help="render a saved audit JSON as PDF")
    p.add_argument("audit", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--prepared-for", default="")
    c = sub.add_parser("compare", help="before/after remediation PDF")
    c.add_argument("before", type=Path)
    c.add_argument("after", type=Path)
    c.add_argument("--out", type=Path)
    c.add_argument("--prepared-for", default="")
    args = ap.parse_args(argv)

    if args.cmd == "audit":
        urls = list(args.urls)
        if args.file:
            urls += [ln.strip() for ln in args.file.read_text().splitlines()
                     if ln.strip() and not ln.startswith("#")]
        if not urls:
            ap.error("give at least one URL (or --file)")
        for url in urls:
            data = wrap(url, run_audit(url))
            stamp = data["audited_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
            base = f"{slug(url)}-{stamp[:15]}Z"
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{base}.json").write_text(json.dumps(data, indent=2))
            pdf = render_audit(data, args.out / f"{base}.pdf", args.prepared_for)
            r = data["result"]
            print(f"{url}: score {r.get('score')} ({r.get('grade')}), "
                  f"{len(r.get('violations') or [])} failed rule(s)\n  JSON {args.out / base}.json\n  PDF  {pdf}")
    elif args.cmd == "pdf":
        data = load(args.audit)
        out = render_audit(data, args.out or args.audit.with_name(
            args.audit.name.removesuffix(".json") + ".pdf"), args.prepared_for)
        print(out)
    else:
        before, after = load(args.before), load(args.after)
        out = render_compare(before, after, args.out or args.after.with_name(
            args.after.name.removesuffix(".json") + "-remediation.pdf"), args.prepared_for)
        d = diff(before, after)
        print(f"resolved {len(d['resolved'])}, still open {len(d['still_open'])}, "
              f"new {len(d['new'])}\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
