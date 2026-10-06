# SEO Score API: AI skills

Open-source skills that let Claude, ChatGPT, Gemini (or a plain terminal) run
[SEO Score API](https://seoscoreapi.com) audits and hand back something a person can
read.

| Skill | What you get |
|---|---|
| [`ada-report`](skills/ada-report) | ADA / WCAG 2.1 AA accessibility audits as **dated PDF reports**: every issue with its WCAG success criterion, impact, affected elements and the fix, plus a **before/after remediation report**. Optional **tracker inventory** (`--trackers`): every analytics, ad, session-replay and chat tool the page loads. Raw JSON saved with a SHA-256 fingerprint. |
| [`seo-score`](skills/seo-score) | SEO audits, Deep Audits, batch audits and score comparisons, inline in your assistant. |

**Unbranded, so it goes out under your name.** The PDF carries no vendor branding (text,
footer or metadata). Add your firm, logo, client/matter and reviewer with a flag, or
leave the top of page 1 clear for letterhead. Every report ends with a Review block
(reviewed by / signature / title / date).

**Samples** (run on our own homepage; the matching JSON is next to them):
[unbranded](examples/sample-seoscoreapi.com-audit.pdf) ·
[with a (fictitious) firm's logo and signature](examples/sample-branded-audit.pdf)

## Quick start (terminal)

```bash
git clone https://github.com/SeoScoreAPI/ai-skills && cd ai-skills
pip install fpdf2
export SEO_SCORE_API_KEY="your_key"          # https://seoscoreapi.com
python3 skills/ada-report/scripts/ada_report.py audit https://example.com \
    --firm "Your Firm LLP" --logo logo.png --prepared-for "Client / Matter" --prepared-by "Your Name"
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
