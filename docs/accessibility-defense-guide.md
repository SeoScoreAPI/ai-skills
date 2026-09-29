# Using automated accessibility audits in ADA website defense

A practical workflow for firms that defend website-accessibility claims under ADA
Title III, using SEO Score API with the AI assistant you already use (Claude or ChatGPT)
or a terminal. You get PDFs, not JSON.

> This is a tooling guide, not legal advice. Automated testing finds a subset of WCAG
> 2.1 AA issues; use it alongside a qualified manual accessibility review.

## The workflow

**1. Intake: document what's there.** When a demand letter or complaint arrives, audit
the pages it names, plus the home, contact, and any checkout, booking, or form pages.

> "Run an accessibility audit on these five URLs for matter 2026-114 and give me the PDFs."

Each page gets a PDF and its raw JSON, both stamped with the UTC time and a SHA-256
fingerprint of the result. Keep both in the matter file. The PDF lists every failed WCAG
2.1 AA rule with its success criterion (for example *1.4.3 Contrast (Minimum), AA*), its
impact, the affected elements, and the fix.

**2. Triage with the client's developer.** The issues table is sorted by impact
(critical, then serious). Each issue carries a plain-English fix and the exact element
(CSS selector and HTML), so the developer can start without an expert report.

**3. Remediation: prove what changed.** Once the fixes are live, audit the same URLs
again, then compare:

> "Compare the before and after audits for the contact page."

The remediation report shows what was **resolved**, what is **still open** (with element
counts before and after), and anything **new**, with both dates and both fingerprints.

**4. Monitoring (optional).** Re-audit on a schedule during a settlement's compliance
period; each run is another dated record.

## Setting it up

| You use | Setup | Time |
|---|---|---|
| Claude (Code or Desktop) | Install the [`ada-report`](../skills/ada-report) skill | 5 min |
| ChatGPT | Custom GPT with the audit action: [chatgpt/](../chatgpt/README.md) | 10 min |
| Neither | Run the script in a terminal: [README](../README.md#quick-start-terminal) | 5 min |

You need an SEO Score API key on a paid plan: Starter ($5/mo, 5 accessibility audits),
Pro ($39/mo, 100, one year of history), or Ultra ($99/mo, 500, unlimited history).
[seoscoreapi.com](https://seoscoreapi.com/#pricing)

## What the fingerprint is for

The audit JSON holds the raw result exactly as the API returned it. The SHA-256
fingerprint printed on the PDF is computed over that result; recomputing it later
(`sha256` of the result with sorted keys) shows the file hasn't been altered. It is a
record-keeping aid, not a chain-of-custody service.

## Limits to keep in mind

- Automated rules (axe-core) catch a portion of WCAG issues; many criteria need a person
  (meaningful alt text, keyboard use of complex widgets, caption accuracy).
- A clean automated result is not proof of conformance.
- Results reflect the page as served to the testing browser at that moment; content
  behind logins or on other pages isn't covered unless you audit it.
