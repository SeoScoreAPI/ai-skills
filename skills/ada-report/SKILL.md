---
name: ada-report
description: Run ADA / WCAG 2.1 AA accessibility audits on websites and produce dated, readable PDF reports, including before/after remediation reports. Triggers on requests like "accessibility audit", "ADA audit", "WCAG report", "check this site for ADA issues", "give me a PDF of the accessibility issues", or "compare the before and after audits".
allowed-tools: Bash(python3:*), Bash(pip:*), Read
user-invocable: true
---

# ADA Report: accessibility audits as dated PDFs

Turns the SEO Score API accessibility audit (`/audit/accessibility`, axe-core in a real
browser, WCAG 2.1 A/AA) into reports a non-developer can read. The output is a PDF plus
the raw JSON, saved with the UTC time and a SHA-256 fingerprint so the result can be
shown to be unchanged later.

## Setup (once)

```bash
pip install fpdf2
export SEO_SCORE_API_KEY="your_key"   # https://seoscoreapi.com (accessibility audits need a paid plan, from $5/mo)
```

## Commands

```bash
# Audit one or more pages: writes <site>-<UTC time>.json and .pdf per URL
python3 skills/ada-report/scripts/ada_report.py audit https://example.com https://example.com/contact \
    --out accessibility-audits --prepared-for "Matter 2026-114"

# Audit a list of URLs (one per line, # for comments)
python3 skills/ada-report/scripts/ada_report.py audit --file urls.txt --out accessibility-audits

# Re-render the PDF for a saved audit
python3 skills/ada-report/scripts/ada_report.py pdf accessibility-audits/example.com-20260929T2150Z.json

# Before/after remediation report (resolved / still open / new)
python3 skills/ada-report/scripts/ada_report.py compare before.json after.json --out remediation.pdf
```

## User intent mapping

| User says | Do |
|---|---|
| "audit example.com for accessibility" / "ADA check" | `audit https://example.com` |
| "audit these pages" / "the whole list" | `audit <url> <url> ...` or `audit --file urls.txt` |
| "put the client/matter name on it" | add `--prepared-for "..."` |
| "they fixed it, run it again and show what changed" | `audit` the same URL, then `compare <old json> <new json>` |
| "make the PDF again" | `pdf <json>` |

## After running

1. Tell the user where the PDF and JSON were saved. **Keep the JSON**: it is the record
   the fingerprint in the PDF refers to.
2. Summarize in plain language: score, number of failed WCAG rules and elements, the
   highest-impact issues first (critical, then serious), each with its WCAG criterion.
3. Always include the limits: automated testing finds a subset of WCAG issues; a clean
   result is not proof of conformance, and the report is not a legal opinion.
4. Never edit the JSON by hand; re-run the audit instead (an edited file no longer matches
   its fingerprint and the script warns about it).

## What the report contains

- URL, date/time (UTC), standard, method, HTTP status, SHA-256 fingerprint
- Summary: score and grade, rules checked, failed/passed, needs manual review
- Issues table: WCAG success criterion (number, name, level), impact, element count
- Details: description, the fix, up to 5 affected elements (CSS selector, HTML snippet,
  element-specific fix such as the measured contrast ratio)
- Best-practice findings (not WCAG failures) and items needing manual review
- Scope and limits

Plain Python (stdlib + fpdf2), so it runs the same from Claude, ChatGPT (with code
execution), Gemini, Cursor, or a terminal.
