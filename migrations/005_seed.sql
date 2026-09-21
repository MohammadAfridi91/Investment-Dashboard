-- ═══════════════════════════════════════════════════════════════════════════
-- 005_seed.sql
-- Seed data: sector index placeholders, auditor list, holiday sentinel
-- ═══════════════════════════════════════════════════════════════════════════

-- Sector index names (placeholder rows; actual data populated by ingestion)
-- No-op insert — ingestion writes actual rows. Listed here for documentation.
-- NIFTY IT, NIFTY PHARMA, NIFTY AUTO, NIFTY FMCG, NIFTY METAL, NIFTY ENERGY,
-- NIFTY REALTY, NIFTY INFRA, NIFTY MEDIA, NIFTY CAPITAL GOODS,
-- NIFTY CONSUMER DURABLES, NIFTY HEALTHCARE, NIFTY INDIA DEFENCE,
-- NIFTY RAILWAYS, NIFTY CHEMICALS

-- Universe placeholder — populated by nse_universe.py
-- No seed rows here.

-- Holidays are loaded from config/nse_holidays.json at app startup.
-- No DB seed needed.
