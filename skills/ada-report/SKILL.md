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

On Windows PowerShell: `$env:SEO_SCORE_API_KEY="your_key"`. If `python3` isn't found, use `python`.

## Commands

Each `audit` of a URL counts as one accessibility audit on your plan (Starter includes 5 a
month). `pdf` and `compare` work from saved JSON and cost nothing, so re-render with
those rather than re-auditing. `--help` on any command lists every option.

```bash
# Audit one or more pages: writes <site>-<UTC time>.json and .pdf per URL
python3 skills/ada-report/scripts/ada_report.py audit https://example.com https://example.com/contact \
    --out accessibility-audits --prepared-for "Matter 2026-114"

# Put YOUR firm on it (all optional). Without these the report is fully unbranded.
python3 skills/ada-report/scripts/ada_report.py audit https://example.com \
    --firm "Sample & Partners LLP" --logo firm-logo.png \
    --prepared-for "Acme Corp. / Matter 2026-114" --prepared-by "Jane Doe, Esq." \
    --signature jane-signature.png

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
| "put our firm name / logo on it" | add `--firm "..."` and/or `--logo path.png` (PNG or JPG) |
| "I'm the reviewer" / "add my signature" | `--prepared-by "Name"`, and `--signature path.png` if they have an image |
| "no signature lines" | `--no-signature-block` |
| "include the risk rating" | `--include-risk` (the API's automated lawsuit-risk flag; off by default) |
| "they fixed it, run it again and show what changed" | `audit` the same URL, then `compare <old json> <new json>` |
| "make the PDF again" | `pdf <json>` |

## If something goes wrong

| Message | What it means | What to do |
|---|---|---|
| "the website could not be audited" (HTTP 422) | The site blocks automated browsers, or the page didn't load | Try another page on the same site, or ask the site owner to allow the audit. Not counted against the plan. |
| "your plan does not include accessibility audits" (403) | Free plan, or the monthly allowance is used | Upgrade or wait for the next month: seoscoreapi.com/#pricing |
| "the API key was not accepted" (401) | Key missing or mistyped | Re-set `SEO_SCORE_API_KEY` without quotes or spaces |
| "image not found" | The logo or signature path is wrong | Check the file path; PNG or JPG only |
| "Missing dependency" | fpdf2 isn't installed | `pip install fpdf2` |

## After running

1. Tell the user where the PDF and JSON were saved. **Keep the JSON**: it is the record
   the fingerprint in the PDF refers to.
2. Summarize in plain language: score, number of failed WCAG rules and elements, the
   highest-impact issues first (critical, then serious), each with its WCAG criterion.
3. Always include the limits: automated testing finds a subset of WCAG issues; a clean
   result is not proof of conformance, and the report is not a legal opinion.
4. Never edit the JSON by hand; re-run the audit instead (an edited file no longer matches
   its fingerprint and the script warns about it).

## Branding: unbranded by default

The PDF carries **no vendor branding** (not in the text, the footer, or the PDF
metadata), so it can go out under the firm's name.
- `--firm` prints the firm name top-right on every page and in the footer; `--logo` adds a
  PNG/JPG logo top-left on every page. Without a logo, the top of page 1 is left clear so a
  logo or letterhead can be stamped on later (Acrobat, Preview) or printed on letterhead.
- Every report ends with a **Review** block: Reviewed by / Signature / Title / Date lines.
  `--prepared-by` fills the name; `--signature` places a signature image; or sign it by
  hand / e-signature afterwards.
- The API's automated "lawsuit risk" flag is **left out** unless `--include-risk` is given,
  since the report may be shared or produced.
- Firm details work the same on `pdf` (re-render a saved audit) and `compare`.

## What the report contains

- URL, date/time (UTC), standard, method, HTTP status, SHA-256 fingerprint
- Summary: score and grade, rules checked, failed/passed, needs manual review
- Issues table: WCAG success criterion (number, name, level), impact, element count
- Details: description, the fix, up to 5 affected elements (CSS selector, HTML snippet,
  element-specific fix such as the measured contrast ratio)
- Best-practice findings (not WCAG failures) and items needing manual review
- Scope and limits
- Review block (reviewer, signature, title, date)

Plain Python (stdlib + fpdf2), so it runs the same from Claude, ChatGPT (with code
execution), Gemini, Cursor, or a terminal.
