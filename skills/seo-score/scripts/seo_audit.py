#!/usr/bin/env python3
"""SEO Score API — Claude Code CLI wrapper.

Usage:
    seo_audit.py audit <url> [--json]
    seo_audit.py deep <url> [--business-type TYPE] [--json]
    seo_audit.py deep-start <url> [--business-type TYPE] [--json]
    seo_audit.py deep-status <job_id> [--json]
    seo_audit.py deep-usage [--json]
    seo_audit.py batch <url> [<url>...] [--json]
    seo_audit.py competitive <url> <competitor_url> <keyword> [--json]
    seo_audit.py report <domain>
    seo_audit.py scoreboard

Any command also accepts --json (raw output) and --no-color (strip ANSI).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://seoscoreapi.com"
# Deep Site Audit — async, 14k+ checks across 9 sections. Served on the main host
# (POST /site-audit, GET /site-audit/{job_id}, GET /deep-audit/usage). Included on
# Pro/Ultra; other keys spend a purchased Deep Audit credit. Override the host with
# SEO_SCORE_DEEP_AUDIT_URL (SEO_SCORE_ENGINE_URL is still read; the legacy
# https://engine.seoscoreapi.com keeps working).
DEEP_AUDIT_URL = (
    os.environ.get("SEO_SCORE_DEEP_AUDIT_URL")
    or os.environ.get("SEO_SCORE_ENGINE_URL")
    or BASE_URL
).rstrip("/")
API_KEY = os.environ.get("SEO_SCORE_API_KEY", "")


def _request(method, path, headers=None, body=None):
    """Make an HTTP request and return parsed JSON."""
    url = f"{BASE_URL}{path}"
    hdrs = headers or {}
    data = json.dumps(body).encode() if body else None
    if data:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            err = json.loads(err_body)
        except json.JSONDecodeError:
            err = {"detail": err_body}
        print(f"Error {e.code}: {err.get('detail', err)}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def _deep_usage_path():
    """Main host: /deep-audit/usage (its /usage is the per-URL allowance).
    Legacy engine host: /usage."""
    host = DEEP_AUDIT_URL.split("://", 1)[-1]
    return "/usage" if host.startswith("engine.") else "/deep-audit/usage"


def _engine_request(method, path, headers=None, body=None):
    """Make an HTTP request against the Deep Site Audit API and return parsed JSON.

    Unlike _request, this returns (status_code, parsed_body) rather than exiting
    on error, so callers can handle 429 (quota/queue) and 401/403 (auth) cleanly.
    """
    url = f"{DEEP_AUDIT_URL}{path}"
    hdrs = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except json.JSONDecodeError:
            return e.code, {}
    except urllib.error.URLError as e:
        print(f"Connection error reaching Deep Site Audit at {DEEP_AUDIT_URL}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def _ensure_scheme(url):
    """Add https:// if no scheme present."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

GRADE_COLORS = {
    "A+": "\033[1;32m", "A": "\033[1;32m", "A-": "\033[32m",
    "B+": "\033[1;33m", "B": "\033[33m", "B-": "\033[33m",
    "C+": "\033[1;93m", "C": "\033[93m", "C-": "\033[93m",
    "D+": "\033[1;91m", "D": "\033[91m", "D-": "\033[91m",
    "F": "\033[1;31m",
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _color_grade(grade):
    color = GRADE_COLORS.get(grade, "")
    return f"{color}{grade}{RESET}"


def _bar(value, width=20):
    filled = round(value / 100 * width)
    return f"[{'#' * filled}{'.' * (width - filled)}]"


def _print_audit(result):
    """Pretty-print a single audit result."""
    url = result.get("url", "?")
    score = result.get("score", 0)
    grade = result.get("grade", "?")

    print(f"\n{BOLD}SEO Audit: {url}{RESET}")
    print(f"{'=' * 60}")
    print(f"  Score: {BOLD}{score:.1f}{RESET} / 100   Grade: {_color_grade(grade)}")
    print()

    # Category breakdowns
    categories = result.get("categories", {})
    if categories:
        print(f"{BOLD}Category Scores:{RESET}")
        for cat, data in categories.items():
            cat_score = data.get("score", 0)
            cat_max = data.get("max", 1)
            pct = (cat_score / cat_max * 100) if cat_max else 0
            label = cat.replace("_", " ").title()
            print(f"  {label:<20} {_bar(pct)} {cat_score}/{cat_max} ({pct:.0f}%)")
        print()

    # Top priorities
    priorities = result.get("priorities", [])
    if priorities:
        print(f"{BOLD}Top Priorities:{RESET}")
        for i, p in enumerate(priorities[:5], 1):
            if isinstance(p, dict):
                severity = p.get("severity", "").upper()
                issue = p.get("issue", "")
                fix = p.get("fix", "")
                print(f"  {i}. [{severity}] {issue}")
                if fix:
                    print(f"     -> {fix}")
            else:
                print(f"  {i}. {p}")
        print()

    # Summary stats
    checks = result.get("checks", {})
    if checks:
        passed = sum(1 for v in checks.values() if v.get("pass"))
        total = len(checks)
        print(f"{DIM}Checks: {passed}/{total} passed{RESET}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_audit(url, raw_json=False):
    """Audit a single URL."""
    url = _ensure_scheme(url)
    encoded = urllib.parse.quote(url, safe="")

    if API_KEY:
        result = _request("GET", f"/audit?url={encoded}", headers={"X-API-Key": API_KEY})
    else:
        result = _request("GET", f"/demo-audit?url={encoded}")

    if raw_json:
        print(json.dumps(result, indent=2))
    else:
        _print_audit(result)


def cmd_batch(urls, raw_json=False):
    """Batch audit multiple URLs."""
    if not API_KEY:
        print("Error: Batch audits require an API key.", file=sys.stderr)
        print("Set SEO_SCORE_API_KEY or sign up at https://seoscoreapi.com/docs#signup", file=sys.stderr)
        sys.exit(1)

    urls = [_ensure_scheme(u) for u in urls]
    result = _request(
        "POST", "/audit/batch",
        headers={"X-API-Key": API_KEY},
        body={"urls": urls},
    )

    if raw_json:
        print(json.dumps(result, indent=2))
        return

    results = result.get("results", [])
    print(f"\n{BOLD}Batch Audit — {len(results)} URLs{RESET}")
    print(f"{'=' * 60}")
    for item in results:
        if "error" in item:
            print(f"\n  {item.get('url', '?')}: Error — {item['error']}")
        else:
            _print_audit(item)


def cmd_report(domain):
    """Print the report URL for a domain."""
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    url = f"{BASE_URL}/scoreboard?domain={urllib.parse.quote(domain)}"
    print(f"\nSEO Report for {domain}:")
    print(f"  {url}")
    print(f"\nTo run a fresh audit: python3 {__file__} audit https://{domain}")


def cmd_competitive(url, competitor_url, keyword, raw_json=False):
    """Run a head-to-head competitive audit."""
    if not API_KEY:
        print("Error: Competitive audits require an API key (Pro plan or higher).", file=sys.stderr)
        print("Set SEO_SCORE_API_KEY or sign up at https://seoscoreapi.com/docs#signup", file=sys.stderr)
        sys.exit(1)

    url = _ensure_scheme(url)
    competitor_url = _ensure_scheme(competitor_url)
    result = _request(
        "POST", "/audit/competitive",
        headers={"X-API-Key": API_KEY},
        body={"url": url, "competitor_url": competitor_url, "keyword": keyword},
    )

    if raw_json:
        print(json.dumps(result, indent=2))
        return

    your_score = result.get("your_score", 0)
    comp_score = result.get("competitor_score", 0)
    gap = result.get("competitive_gap", 0)
    score_gap = result.get("score_gap", 0)
    kw_rel = result.get("keyword_relevance", {})

    print(f"\n{BOLD}Competitive Audit: {url} vs {competitor_url}{RESET}")
    print(f"{'=' * 60}")
    print(f"  Keyword: {BOLD}{keyword}{RESET}")
    print(f"  Your Score:       {BOLD}{your_score:.1f}{RESET} / 100")
    print(f"  Competitor Score: {BOLD}{comp_score:.1f}{RESET} / 100")
    print(f"  Score Gap:        {score_gap:+.1f}")
    print(f"  Competitive Gap:  {BOLD}{gap}{RESET} / 100")
    print(f"  Keyword Relevance: You {kw_rel.get('yours', 0)} vs Competitor {kw_rel.get('competitor', 0)}")
    print()

    gaps = result.get("gaps", [])
    if gaps:
        print(f"{BOLD}Top Gaps (where competitor beats you):{RESET}")
        for i, g in enumerate(gaps[:8], 1):
            print(f"  {i}. [{g['category']}] {g['check']}: you {g['your_score']} vs them {g['competitor_score']} (gap: {g['gap']})")
        print()

    action_items = result.get("action_items", [])
    if action_items:
        print(f"{BOLD}Action Items:{RESET}")
        for i, item in enumerate(action_items, 1):
            print(f"  {i}. {item}")
        print()


SECTION_NAMES = {
    "1": "Technical Foundation & Rendering",
    "2": "Crawlability & Site Architecture",
    "3": "Content Quality & Entity Semantics",
    "4": "Core Web Vitals & Performance",
    "5": "Technical SEO & Index Control",
    "6": "Schema, Local, Trust & E-E-A-T",
    "7": "Security & Privacy",
    "8": "Multimodal Content & Media",
    "9": "Off-Site Signals & Reputation",
}


def _print_deep(result):
    """Pretty-print a completed Deep Audit result (0-5 scale scores)."""
    scores = result.get("scores", {})
    cov = result.get("coverage", {})
    findings = result.get("findings", [])

    print(f"\n{BOLD}Deep Audit — {result.get('website_url', '?')}{RESET}")
    print(f"{'=' * 62}")
    lai = scores.get("lai_score")
    grade = scores.get("lai_grade", "")
    if lai is not None:
        print(f"  {BOLD}LAI Score: {lai}/5{RESET}  ({grade})   "
              f"confidence {scores.get('confidence_percent', '?')}%")
    print(f"  AI {scores.get('ai_score', '?')}/5   "
          f"SEO {scores.get('seo_score', '?')}/5   "
          f"Local {scores.get('local_score') if scores.get('local_score') is not None else 'n/a'}")
    print(f"  Tasks scored: {scores.get('tasks_scored', '?')}  "
          f"(passed {scores.get('tasks_passed', '?')}, warned {scores.get('tasks_warned', '?')})")
    print(f"  Coverage: {cov.get('coverage_pct', '?')}% "
          f"({cov.get('implemented_count', '?')}/{cov.get('total_subsections', '?')} subsections, "
          f"{cov.get('hybrid_ai_tasks', 0)} AI checks run)")

    ss = scores.get("section_scores", {})
    if ss:
        print(f"\n{BOLD}Section scores (0-5):{RESET}")
        for k in sorted(ss, key=lambda x: int(x)):
            print(f"  S{k}  {SECTION_NAMES.get(k, ''):34} {_bar(float(ss[k]) * 20)} {ss[k]}")

    if findings:
        print(f"\n{BOLD}Top findings ({len(findings)}):{RESET}")
        for x in findings[:20]:
            ev = x.get("evidence", "")
            if isinstance(ev, (dict, list)):
                ev = json.dumps(ev)
            ev = str(ev).strip()
            if len(ev) > 100:
                ev = ev[:97] + "..."
            sev = x.get("weight") or x.get("severity") or "?"
            print(f"  [{sev:8}] S{x.get('section', '?')} {x.get('task_id', '')}: {ev}")

    print(f"\n  {DIM}Note: findings weighted 'critical' for schema/local types that don't")
    print(f"  apply to a site's business model (e.g. Event/JobPosting/GBP on a")
    print(f"  directory) are expected — focus on the checks relevant to the site.{RESET}")


def _deep_key_or_exit():
    if not API_KEY:
        print("Error: Deep Audit needs an API key (Pro/Ultra, or one with Deep Audit credits).", file=sys.stderr)
        print("Set SEO_SCORE_API_KEY.", file=sys.stderr)
        sys.exit(1)
    return {"X-API-Key": API_KEY}


def _deep_start(url, business_type=None):
    """Start a Deep Site Audit job and return its job_id (exits on error)."""
    hdrs = _deep_key_or_exit()
    body = {"url": _ensure_scheme(url)}
    if business_type:
        body["business_type"] = business_type
    status, resp = _engine_request("POST", "/site-audit", headers=hdrs, body=body)
    if status == 429:
        print(f"Deep Audit unavailable right now: {resp.get('detail', 'quota or queue limit')}", file=sys.stderr)
        sys.exit(1)
    if status == 402:
        print(f"No Deep Audits left on this key: {resp.get('detail', '')} "
              f"Pro includes 20/month, Ultra 100/month; credits work on any plan.", file=sys.stderr)
        sys.exit(1)
    if status in (401, 403):
        print(f"Auth failed for Deep Audit ({status}). {resp.get('detail', '')}", file=sys.stderr)
        sys.exit(1)
    if status not in (200, 202) or "job_id" not in resp:
        print(f"Failed to start Deep Audit (HTTP {status}): {resp.get('detail', resp)}", file=sys.stderr)
        sys.exit(1)
    return resp


def cmd_deep(url, raw_json=False, business_type=None, poll_seconds=6, timeout_seconds=900):
    """Run an async Deep Site Audit (14k+ checks) and poll to completion."""
    hdrs = _deep_key_or_exit()
    job_id = _deep_start(url, business_type)["job_id"]
    if not raw_json:
        print(f"Deep Audit queued (job {job_id}). This runs thousands of checks and "
              f"typically takes 1-3 minutes...", file=sys.stderr)

    start = time.time()
    last_stage = None
    while True:
        time.sleep(poll_seconds)
        status, p = _engine_request("GET", f"/site-audit/{job_id}", headers=hdrs)
        if status != 200:
            print(f"Error polling Deep Audit (HTTP {status}): {p.get('detail', p)}", file=sys.stderr)
            sys.exit(1)
        state = p.get("status")
        if not raw_json:
            stage = f"{p.get('progress', 0)}% — {p.get('stage', '')}"
            if p.get("queue_position") is not None:
                stage = f"queued #{p['queue_position']} (eta ~{p.get('eta_seconds', '?')}s)"
            if stage != last_stage:
                print(f"  [{int(time.time() - start)}s] {stage}", file=sys.stderr)
                last_stage = stage
        if state == "completed":
            if raw_json:
                print(json.dumps(p, indent=2))
            else:
                _print_deep(p.get("result", {}))
            return
        if state == "failed":
            print(f"Deep Audit failed: {p.get('error', 'unknown error')}", file=sys.stderr)
            sys.exit(1)
        if time.time() - start > timeout_seconds:
            print(f"Deep Audit still running after {timeout_seconds // 60} minutes. "
                  f"Check later: seo_audit.py deep-status {job_id}", file=sys.stderr)
            sys.exit(1)


def cmd_deep_start(url, raw_json=False, business_type=None):
    """Queue a Deep Site Audit and print the job id without waiting."""
    job = _deep_start(url, business_type)
    if raw_json:
        print(json.dumps(job, indent=2))
    else:
        print(f"Deep Audit queued: job {job['job_id']}")
        print(f"  Check it with: seo_audit.py deep-status {job['job_id']}")


def cmd_deep_status(job_id, raw_json=False):
    """Print a Deep Site Audit job's status (and the result once completed)."""
    hdrs = _deep_key_or_exit()
    status, p = _engine_request("GET", f"/site-audit/{urllib.parse.quote(job_id, safe='')}", headers=hdrs)
    if status == 404:
        print("Deep Audit job not found (unknown id, or started by a different key).", file=sys.stderr)
        sys.exit(1)
    if status != 200:
        print(f"Error polling Deep Audit (HTTP {status}): {p.get('detail', p)}", file=sys.stderr)
        sys.exit(1)
    if raw_json:
        print(json.dumps(p, indent=2))
        return
    state = p.get("status")
    if state == "completed":
        _print_deep(p.get("result", {}))
    elif state == "failed":
        print(f"Deep Audit failed: {p.get('error', 'unknown error')}")
    elif state == "queued":
        print(f"Queued #{p.get('queue_position', '?')} (eta ~{p.get('eta_seconds', '?')}s)")
    else:
        print(f"{state}: {p.get('progress', 0)}% — {p.get('stage', '')}")


def cmd_deep_usage(raw_json=False):
    """Print Deep Site Audits used/remaining this month."""
    hdrs = _deep_key_or_exit()
    status, p = _engine_request("GET", _deep_usage_path(), headers=hdrs)
    if status != 200:
        print(f"Error reading Deep Audit usage (HTTP {status}): {p.get('detail', p)}", file=sys.stderr)
        sys.exit(1)
    if raw_json:
        print(json.dumps(p, indent=2))
        return
    sa = p.get("site_audit", {})
    print(f"Deep Audits this month ({p.get('tier', '?')}): {sa.get('used', '?')} used, "
          f"{sa.get('remaining', '?')} remaining")


def cmd_scoreboard():
    """Print the scoreboard URL."""
    print(f"\nSEO Score Public Scoreboard:")
    print(f"  {BASE_URL}/scoreboard")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    raw_json = "--json" in args
    if raw_json:
        args.remove("--json")

    if "--no-color" in args:
        args.remove("--no-color")
        global RESET, BOLD, DIM, GRADE_COLORS
        RESET = BOLD = DIM = ""
        GRADE_COLORS = {}

    if not args:
        print(__doc__)
        sys.exit(1)

    business_type = None
    if "--business-type" in args:
        i = args.index("--business-type")
        if i + 1 >= len(args):
            print("--business-type needs a value (saas, local_service, ecommerce, storefront, blog, publisher)", file=sys.stderr)
            sys.exit(1)
        business_type = args[i + 1]
        del args[i:i + 2]
        if not args:
            print(__doc__)
            sys.exit(1)

    cmd = args[0]

    if cmd == "audit":
        if len(args) < 2:
            print("Usage: seo_audit.py audit <url> [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_audit(args[1], raw_json)

    elif cmd == "deep":
        if len(args) < 2:
            print("Usage: seo_audit.py deep <url> [--business-type TYPE] [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_deep(args[1], raw_json, business_type)

    elif cmd == "deep-start":
        if len(args) < 2:
            print("Usage: seo_audit.py deep-start <url> [--business-type TYPE] [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_deep_start(args[1], raw_json, business_type)

    elif cmd == "deep-status":
        if len(args) < 2:
            print("Usage: seo_audit.py deep-status <job_id> [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_deep_status(args[1], raw_json)

    elif cmd == "deep-usage":
        cmd_deep_usage(raw_json)

    elif cmd == "batch":
        if len(args) < 2:
            print("Usage: seo_audit.py batch <url1> <url2> ... [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_batch(args[1:], raw_json)

    elif cmd == "report":
        if len(args) < 2:
            print("Usage: seo_audit.py report <domain>", file=sys.stderr)
            sys.exit(1)
        cmd_report(args[1])

    elif cmd == "competitive":
        if len(args) < 4:
            print("Usage: seo_audit.py competitive <url> <competitor_url> <keyword> [--json]", file=sys.stderr)
            sys.exit(1)
        cmd_competitive(args[1], args[2], " ".join(args[3:]), raw_json)

    elif cmd == "scoreboard":
        cmd_scoreboard()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
