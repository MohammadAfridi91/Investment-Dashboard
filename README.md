# Dalal Street Quantitative & Forensic Automation Engine — v6.4

Decision-support tool. Generates pre-flight trade cards. Human reads cards and decides.
No execution. No paper trading. No backtest gating.

## Status
- Week 1 of 6 complete.
- Live modules: universe, bhavcopy, index prices, market-regime skeleton, pipeline health.
- Week 2+: derivatives, surveillance, institutional, corporate actions, Screener, forensic indicators, cards.

## Bootstrap
1. `docs/supabase_bootstrap.md` — create Supabase project + apply migrations.
2. `docs/github_bootstrap.md` — create private repo + add secrets.
3. `cp .env.example .env` and fill values.
4. `pip install -r requirements.txt`
5. `make db-migrate`
6. `make test`

## Scheduled (GitHub Actions, UTC-only)
| Job | Cron (UTC) | IST |
| :--- | :--- | :--- |
| Pre-market | `15 3 * * 1-5` | 08:45 |
| EOD | `15 13 * * 1-5` | 18:45 |
| Heartbeat | `30 14 * * 1-5` | 20:00 |

## Compliance
SEBI-RA personal use only. No redistribution.

## Deployment notes (compliance archive)

Before the next EOD run:

1. Apply `migrations/008_compliance_report_archive.sql` (append-only, byte-exact report archive).
2. Optional: if you hold a SEBI Research Analyst registration, add the GitHub Actions secret
   `SEBI_RA_REGISTRATION_NUMBER` (format `INH#########`). Without it, reports state that no
   registration is held. A malformed value fails the run.

Pipeline run status is `SUCCESS`, `PARTIAL` (optional source or a few symbols failed; exit 0 with a
warning annotation) or `FAILED` (prices/technicals/desks/archive failed; exit 1).
