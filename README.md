# Dalal Street Quantitative & Forensic Automation Engine (v6.4)

Personal decision-support tool. Generates pre-flight trade cards for human
review. No execution, no paper trading, no backtest gating.

## Scope

- Daily EOD scan of Nifty 500 + MidSmall 400 universe (~900 stocks)
- Non-BFSI hard exclusion (Layer 1)
- Fatal Dalal Street Red Flags (Layer 2)
- Card 1: Tactical Swing pre-flight checklist (Layer 3a)
- Card 2: Strategic Core pre-flight checklist (Layer 3b)
- SEBI-RA compliance: research report archive, disclosure snapshot, UPSI
  logging, 5-year retention
- Point-in-time financials (hybrid: 3-year backfill + forward)

**Explicitly out of scope:** Telegram bot, Streamlit dashboard, order
execution, paper trading, offline backtesting, slippage/fill simulation,
BFSI/NBFC analysis, intraday data, guaranteed-return language, public
redistribution (personal RA tool only), self-hosted runner.

## Deployment

GitHub Actions only — no always-on server.

| Workflow | Trigger | Purpose |
|---|---|---|
| `eod_pipeline.yml` | 18:45 IST weekdays (cron) + manual | Full daily scan → Supabase |
| `premarket.yml` | 08:45 IST weekdays (cron) + manual | Surveillance lists, board meetings |
| `heartbeat.yml` | 20:00 IST weekdays (cron) + manual | Alerts if EOD run goes stale |
| `backfill.yml` | Manual only | One-time historical backfill |

## Setup

1. Create a Supabase project and run `sql/schema.sql` against it (currently
   only the `universe` table — more to come).
2. In GitHub: **Settings → Secrets and Variables → Actions**, add:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`

   The plan recommends scoping these to a `production` environment
   restricted to the `main` branch (Section 3.5).
3. Push this repo to GitHub. Scheduled runs start on the next matching
   weekday; use "Run workflow" in the Actions tab to trigger manually
   before then.

## Build status

This scaffold contains only what has been fully specified so far — nothing
below has been guessed or stubbed with placeholder logic.

- [x] All 4 GitHub Actions workflows
- [x] `universe` table (1 of 16)
- [ ] Remaining 15 tables
- [ ] Configuration module (Section 5)
- [ ] Ingestion modules (Section 6)
- [ ] Indicator modules (Section 7)
- [ ] Filter modules (Section 8)
- [ ] Engine modules — Card 1 / Card 2 scoring (Section 9)
- [ ] SEBI-RA compliance module (Section 10)
- [ ] Data source integrations (Section 11)
- [ ] Project structure conventions (Section 12) — this scaffold's layout
      is provisional until that section arrives
- [ ] `run_daily_pipeline.py`, `scripts/heartbeat_check.py`,
      `scripts/backfill.py` — entry points the workflows above already
      call by name, not yet written since their logic depends on the
      modules above
