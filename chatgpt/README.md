# Accessibility reports in ChatGPT (Custom GPT)

Build a private Custom GPT that runs SEO Score API accessibility audits and hands back a
PDF. About 10 minutes, no code. Needs a ChatGPT plan that can create GPTs and an SEO
Score API key on a paid plan (accessibility audits start at $5/mo).

## 1. Create the GPT

ChatGPT, then **Explore GPTs**, then **Create**, then **Configure**:

- **Name:** Accessibility Audit
- **Instructions:** paste the whole of [`instructions.md`](instructions.md)
- **Capabilities:** turn on **Code Interpreter & Data Analysis** (it builds the PDF)
- **Knowledge:** upload [`../skills/ada-report/scripts/ada_report.py`](../skills/ada-report/scripts/ada_report.py)
  (the GPT reuses its WCAG criteria table and report layout)

## 2. Add the action

**Create new action**:

- **Authentication:** API Key, Auth Type **Custom**, header name `X-API-Key`, and paste
  your SEO Score API key
- **Schema:** paste [`openapi-accessibility.yaml`](openapi-accessibility.yaml)
- **Privacy policy:** `https://seoscoreapi.com/privacy`

Save the GPT as **Only me** (or your workspace). Your key stays in the action, not in
the chat.

## 3. Use it

> Audit https://example.com for accessibility and give me the PDF.

> Here are the before and after JSON files: what was fixed?

The GPT calls the audit, keeps the raw JSON (download it too: it's your record), and
builds a PDF with the date, each issue's WCAG criterion, impact, affected elements and
the fix, plus the scope-and-limits statement.

## Notes

- ChatGPT can't install packages. If `fpdf` isn't available in Code Interpreter, the
  instructions tell the GPT to build the same report with `reportlab`, which is.
- For audits of many pages, or reports you need to reproduce exactly, use the
  command-line skill in [`../skills/ada-report`](../skills/ada-report): same report, run
  locally or from Claude.
