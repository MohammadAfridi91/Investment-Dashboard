-- ═══════════════════════════════════════════════════════════════════════════
-- 008_enable_rls_remaining_tables.sql
--
-- Deviation from the original plan: 007's comment justified leaving these
-- 10 tables without RLS by reasoning "no policy = no access" — that's only
-- true when RLS is ENABLED with zero policies (default-deny). With RLS OFF
-- entirely, Supabase's default grants mean the anon/authenticated roles can
-- read AND write every row. Nothing in this system ever uses the anon key
-- (no dashboard, no public client), so the practical exposure was low, but
-- there was no upside to leaving it open either. Decided to close it.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE universe              ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_prices           ENABLE ROW LEVEL SECURITY;
ALTER TABLE benchmark_prices       ENABLE ROW LEVEL SECURITY;
ALTER TABLE sector_indices         ENABLE ROW LEVEL SECURITY;
ALTER TABLE corporate_events       ENABLE ROW LEVEL SECURITY;
ALTER TABLE corporate_actions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE derivative_metrics     ENABLE ROW LEVEL SECURITY;
ALTER TABLE technical_indicators   ENABLE ROW LEVEL SECURITY;
ALTER TABLE auditor_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_regime          ENABLE ROW LEVEL SECURITY;

-- No policies defined on these either. Service-role key (used by the
-- pipeline exclusively) bypasses RLS regardless. Anon/authenticated get
-- default-deny, matching the other 7 tables from 007.
