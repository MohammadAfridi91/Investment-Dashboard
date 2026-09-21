-- ═══════════════════════════════════════════════════════════════════════════
-- 007_pipeline_health.sql
-- Monitoring table for pipeline heartbeat (v6.5 addition)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS pipeline_health (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    workflow VARCHAR(50) NOT NULL,       -- 'eod', 'premarket', 'backfill'
    status VARCHAR(20) NOT NULL,          -- 'SUCCESS', 'FAILED', 'DELAYED'
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds INT,
    rows_processed BIGINT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pipeline_health_run_id UNIQUE (run_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_health_workflow_started
    ON pipeline_health (workflow, started_at DESC);

-- ─────────────── RLS ───────────────
ALTER TABLE trade_check_cards        ENABLE ROW LEVEL SECURITY;
ALTER TABLE sebi_compliance_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE forensic_financials      ENABLE ROW LEVEL SECURITY;
ALTER TABLE surveillance_registry    ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutional_deals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_health          ENABLE ROW LEVEL SECURITY;

-- No policies defined. Service-role key bypasses RLS.
-- Anon key blocked by default (no policy = no access).
