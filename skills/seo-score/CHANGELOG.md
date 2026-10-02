# Changelog (seo-score skill)

## 1.1.0 (2026-10-02)

- Deep Audit runs on the main host, `https://seoscoreapi.com` (`POST /site-audit`,
  `GET /site-audit/{job_id}`, `GET /deep-audit/usage`), instead of
  `engine.seoscoreapi.com`. Override with `SEO_SCORE_DEEP_AUDIT_URL`
  (`SEO_SCORE_ENGINE_URL` still read).
- New commands: `deep-start <url>`, `deep-status <job_id>`, `deep-usage`.
- `--business-type` for `deep` / `deep-start`.
- Clear message on 402 (no Deep Audits left); "still running" timeout points to
  `deep-status`.
- Tests: `pytest skills/seo-score/tests`.

## 1.0.0

- `audit`, `deep`, `batch`, `competitive`, `report`, `scoreboard`.
