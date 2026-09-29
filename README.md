# SEO Score API: AI skills

Open-source skills that let Claude, ChatGPT, Gemini (or a plain terminal) run
[SEO Score API](https://seoscoreapi.com) audits and hand back something a person can
read.

| Skill | What you get |
|---|---|
| [`ada-report`](skills/ada-report) | ADA / WCAG 2.1 AA accessibility audits as **dated PDF reports**: every issue with its WCAG success criterion, impact, affected elements and the fix, plus a **before/after remediation report**. Raw JSON saved with a SHA-256 fingerprint. |
| [`seo-score`](skills/seo-score) | SEO audits, Deep Audits, batch audits and score comparisons, inline in your assistant. |

**Sample report:** [examples/sample-seoscoreapi.com-audit.pdf](examples/sample-seoscoreapi.com-audit.pdf)
(we ran it on our own site; the matching JSON is next to it).

## Quick start (terminal)

```bash
git clone https://github.com/SeoScoreAPI/ai-skills && cd ai-skills
pip install fpdf2
export SEO_SCORE_API_KEY="your_key"          # https://seoscoreapi.com
python3 skills/ada-report/scripts/ada_report.py audit https://example.com
```

Accessibility audits need a paid plan (Starter, $5/mo, includes 5 a month; Pro, $39/mo,
100; Ultra, $99/mo, 500). SEO audits work on the free tier. [Pricing](https://seoscoreapi.com/#pricing)

## Use it with Claude

**Claude Code:** copy the skill folder into your skills directory and ask for it by name.

```bash
mkdir -p ~/.claude/skills && cp -r skills/ada-report ~/.claude/skills/
# then, in Claude Code:  "Run an accessibility audit on https://example.com and give me the PDF"
```

**Claude Desktop / claude.ai:** zip the `skills/ada-report` folder and upload it as a
skill (Settings > Capabilities; code execution must be on). The skill calls
seoscoreapi.com, so the code sandbox needs outbound network access to it; if your
workspace blocks that, use Claude Code or the terminal instead.

## Use it with ChatGPT

Build a private Custom GPT with the audit as an action: step-by-step in
[`chatgpt/`](chatgpt/README.md) (about 10 minutes, no code).

## Who uses the accessibility report

- **Law firms defending website-accessibility (ADA Title III) claims:** a dated record
  of what automated testing finds at intake, and a before/after report once the site is
  fixed. See the guide: [docs/accessibility-defense-guide.md](docs/accessibility-defense-guide.md)
- **Agencies and developers:** hand clients a readable report instead of raw JSON.
- **In-house teams:** track remediation page by page.

## Limits, stated plainly

Automated testing finds a subset of WCAG issues. A clean result is not proof of
conformance, and the report is not a legal opinion. Every PDF says so.

## License

MIT. Issues and pull requests welcome.
