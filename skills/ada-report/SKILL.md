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
export SEO_SCORE_API_KEY="your_key"   # https://seoscoreapi.com (accessibility audits need a paid plan, from $9/mo; not needed for --local)
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

# Also list the third-party trackers the page loads (analytics, ad pixels, session replay,
# chat), in the same PDF. Paid plans; no extra audit is counted.
python3 skills/ada-report/scripts/ada_report.py audit https://example.com --trackers

# The site blocks the audit server? Run the same checks on THIS computer instead
# (see "Local runs" below). Same JSON + fingerprinted PDF, marked as a local run.
python3 skills/ada-report/scripts/ada_report.py audit https://example.com --local \
    --machine-label "Office laptop"

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
| "what trackers / pixels are on the site" / "what does it send to third parties" | add `--trackers` to `audit` |
| "the audit says the site blocks automated browsers" / "run it from my computer" | `audit <url> --local` (after the hosted audit returned 422 / blocked) |
| "include the risk rating" | `--include-risk` (the API's automated lawsuit-risk flag; off by default) |
| "they fixed it, run it again and show what changed" | `audit` the same URL, then `compare <old json> <new json>` |
| "make the PDF again" | `pdf <json>` |

## The tracker inventory (`--trackers`)

Adds a section listing each third-party tool the testing browser saw the page load on
one visit: vendor, type, whether it was in the page source or added by a tag manager,
how many requests it made, up to three request URLs as evidence, and the consent tool on
the page if one was detected. It is part of the same fingerprinted result.

**It is an inventory, not a finding.** It does not say whether a tool waited for consent,
what data it received, or whether its use is lawful. Never describe it as a violation,
exposure or risk; report what loaded and let the reader draw conclusions.

## Local runs (`--local`)

Some sites turn away requests from cloud servers, so the hosted audit gets a 422
("blocks automated browsers"). `--local` runs the audit in Chromium on the user's own
computer and connection, which the site usually already lets in:

```bash
pip install fpdf2 playwright
python3 -m playwright install chromium
python3 skills/ada-report/scripts/ada_report.py audit https://example.com --local --machine-label "Office laptop"
```

- **Same checks:** the same axe-core version (4.10.3) and WCAG 2.1 A/AA + best-practice
  rule set as the hosted audit, scored the same way. No API key is used and nothing is
  sent to the audit service.
- **Marked as local:** files end in `-local.json` / `-local.pdf`; the PDF title, footer,
  header rows and limits say it was a local run, with the machine label, OS, network class,
  browser version and the axe-core file's SHA-256. That record sits inside the fingerprinted
  result, so a local run cannot later pass as a hosted one.
- **No personal data:** no IP address, host name or user name is recorded. The network is
  described only by class ("private address behind a router", "carrier-grade NAT",
  "public address"); the machine only by the `--machine-label` the user types, if any.
- **Never gets around bot protection:** the browser's identity is not changed, there is no
  proxy, and bot checks are not solved. If the site refuses this computer too, or shows a
  challenge page, the run stops with a plain message and writes nothing.
- `--headed` shows the browser window while it runs. `--trackers` is hosted-only.
- `compare` works across hosted and local audits and notes when the two ran in different
  places.

## If something goes wrong

| Message | What it means | What to do |
|---|---|---|
| "the website could not be audited" (HTTP 422) | The site blocks automated browsers, or the page didn't load | Run it from this computer with `--local`, try another page on the same site, or ask the site owner to allow the audit. Not counted against the plan. |
| "refused this computer too" / "showed a bot check" (`--local`) | The site blocks this connection as well | Stop. Ask the site owner to allow the audit; never try to get around it |
| "--local needs Playwright" / "could not start Chromium" | Local-mode browser not installed | `pip install playwright && python3 -m playwright install chromium` |
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

Plain Python (stdlib + fpdf2; Playwright only for `--local`), so it runs the same from Claude, ChatGPT (with code
execution), Gemini, Cursor, or a terminal.
