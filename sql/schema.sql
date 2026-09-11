-- ═══════════════════════════════════════════════════════════════════════════
-- DALAL STREET ENGINE v6.4 — COMPLETE SCHEMA
-- Postgres 15+ (Supabase). All DDL below is idempotent.
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 1: universe
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS universe (
    symbol           VARCHAR(30) PRIMARY KEY,
    company_name     TEXT NOT NULL,
    isin             VARCHAR(20) UNIQUE NOT NULL,
    sector           VARCHAR(100),
    industry         VARCHAR(100),
    is_bfsi          BOOLEAN DEFAULT FALSE,
    is_fno           BOOLEAN DEFAULT FALSE,
    is_nifty500      BOOLEAN DEFAULT FALSE,
    is_midsmall400   BOOLEAN DEFAULT FALSE,
    listed_since     DATE,
    raw_payload_checksum VARCHAR(64),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_universe_bfsi       ON universe (is_bfsi);
CREATE INDEX IF NOT EXISTS idx_universe_n500       ON universe (is_nifty500);
CREATE INDEX IF NOT EXISTS idx_universe_midsmall   ON universe (is_midsmall400);

-- ─────────────────────────────────────────────────────────────────────────
-- TABLES 2–16: PENDING
-- ─────────────────────────────────────────────────────────────────────────
-- The implementation plan states 16 tables total. Only Table 1 (universe)
-- was included in what was received so far. The architecture diagram
-- (plan Section 2.2) names four more tables without defining their columns:
--   - daily_price
--   - forensic_financials
--   - trade_check_cards
--   - sebi_compliance_log
-- ...plus at least 11 further tables referenced only as "All 16 tables
-- from Section 4" with no other detail given.
--
-- Nothing below this line has been guessed. Waiting on the rest of
-- Section 4 before adding more DDL to this file.
