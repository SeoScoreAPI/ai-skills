---
name: seo-score
description: Run SEO audits (regular + Deep Audit), check scores, analyze meta tags, and compare sites using the SEO Score API. Triggers on requests like "audit this URL", "deep audit", "check SEO score", "SEO analysis", "meta tag check", or "compare SEO scores".
allowed-tools: Bash(python3:*), Read, WebFetch
user-invocable: true
---

# SEO Score — Inline SEO Auditing

Run SEO audits directly using the SEO Score API.

> Plain Python over the HTTP API: works from Claude, ChatGPT, Gemini or a terminal.
> Run commands from the repo root.

## Quick Start

```bash
# Audit a single URL (works without API key via demo endpoint)
python3 skills/seo-score/scripts/seo_audit.py audit https://example.com

# Deep Audit — async, 14k+ checks across 9 sections (Pro/Ultra, or Deep Audit credits)
python3 skills/seo-score/scripts/seo_audit.py deep https://example.com --business-type saas

# Deep Audit without waiting: start, check back, see what's left this month
python3 skills/seo-score/scripts/seo_audit.py deep-start https://example.com
python3 skills/seo-score/scripts/seo_audit.py deep-status <job_id>
python3 skills/seo-score/scripts/seo_audit.py deep-usage

# Batch audit multiple URLs (requires API key)
python3 skills/seo-score/scripts/seo_audit.py batch https://example.com https://another.com

# Get report URL for a domain
python3 skills/seo-score/scripts/seo_audit.py report example.com

# View the public scoreboard
python3 skills/seo-score/scripts/seo_audit.py scoreboard
```

Every command also accepts `--json` (raw output) and `--no-color` (strip ANSI).

## Environment Setup

Set `SEO_SCORE_API_KEY` for authenticated access (higher rate limits, batch audits):

```bash
export SEO_SCORE_API_KEY="your_api_key_here"
```

Without an API key, single audits use the demo endpoint (rate limited).

## User Intent Mapping

| User says | Command |
|---|---|
| "audit example.com" | `audit https://example.com` |
| "deep audit example.com" / "run the deep scan" | `deep https://example.com` |
| "start a deep audit and I'll check later" | `deep-start <url>`, then `deep-status <job_id>` |
| "how many deep audits do I have left?" | `deep-usage` |
| "check the SEO score of my site" | `audit <url>` |
| "compare these two sites" | `batch <url1> <url2>` |
| "run SEO checks on these pages" | `batch <url1> <url2> ...` |
| "show the SEO scoreboard" | `scoreboard` |
| "get a report for my domain" | `report <domain>` |
| "what's my SEO grade?" | `audit <url>` |

## Output

The audit returns:
- **Overall score** (0-100) and **letter grade** (A+ to F)
- **Category breakdowns**: Meta, Technical, Social, Performance, Accessibility
- **Top priorities**: The most impactful fixes to improve the score
- **Detailed checks**: Pass/fail for each of the 28 SEO checks

Use `--json` flag on any command for raw JSON output.

### Deep Audit output

`deep` runs a Deep Site Audit on the main host, `https://seoscoreapi.com`
(`POST /site-audit`, then polls `GET /site-audit/{job_id}`). Included on Pro (20/month)
and Ultra (100/month); any other key spends a purchased Deep Audit credit. It posts the
job, polls to completion (progress printed to stderr, ~1-3 min), then prints:
- **LAI score** (0-5) + grade and confidence %, plus AI / SEO / Local sub-scores
- **Section scores (0-5)** for all 9 sections
- **Coverage** (% of subsections with a live checker; AI checks only run when LLM keys are set)
- **Top findings** with section + task id + evidence

`--business-type` (saas | local_service | ecommerce | storefront | blog | publisher) tunes
which checks apply. `deep-start` / `deep-status` split the run so you don't block, and
`deep-usage` reads `GET /deep-audit/usage` (used / remaining this month).

Override the Deep Audit host with `SEO_SCORE_DEEP_AUDIT_URL` if needed
(`SEO_SCORE_ENGINE_URL` is still read; the legacy `https://engine.seoscoreapi.com` works).

## Tips

- Always ensure URLs include the protocol (`https://`)
- For batch audits of more than 10 URLs, split into multiple calls
- After auditing, read the priorities list and suggest fixes to the user
- When comparing sites, highlight score differences and unique issues
- **Deep Audit caveat:** many Section-6 findings are weighted `critical` for schema
  or local-SEO types that don't apply to the site's business model (e.g.
  Event/JobPosting/Product/GBP on a directory or SaaS site). Filter those out and
  focus on findings relevant to what the site actually is before advising fixes.
