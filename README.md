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
