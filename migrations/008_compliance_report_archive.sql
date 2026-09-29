-- ═══════════════════════════════════════════════════════════════════════════
-- 008_compliance_report_archive.sql
-- Durable, byte-exact, append-only archive of SEBI RA research reports.
-- GitHub Actions runners are ephemeral, so files on disk are NOT a retention
-- mechanism; this table is. Rows cannot be updated, and cannot be deleted
-- until their retention_until date has passed.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS compliance_report_archive (
    card_id UUID PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL,
    desk_type VARCHAR(20) NOT NULL,
    eval_date DATE NOT NULL,
    checksum_sha256 CHAR(64) NOT NULL,        -- SHA-256 of report_html bytes (UTF-8)
    json_checksum_sha256 CHAR(64) NOT NULL,   -- SHA-256 of report_json bytes (UTF-8)
    report_html TEXT NOT NULL,
    report_json TEXT NOT NULL,                -- TEXT (not JSONB) to preserve exact bytes
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retention_until DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_archive_symbol_date
    ON compliance_report_archive (symbol, eval_date DESC);

ALTER TABLE compliance_report_archive ENABLE ROW LEVEL SECURITY;
-- No policies: service-role only.

CREATE OR REPLACE FUNCTION forbid_report_archive_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'compliance_report_archive is append-only (UPDATE blocked)';
    END IF;
    IF TG_OP = 'DELETE' AND OLD.retention_until >= CURRENT_DATE THEN
        RAISE EXCEPTION 'compliance_report_archive row is within its retention period (DELETE blocked)';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_report_archive_immutable ON compliance_report_archive;
CREATE TRIGGER trg_report_archive_immutable
    BEFORE UPDATE OR DELETE ON compliance_report_archive
    FOR EACH ROW EXECUTE FUNCTION forbid_report_archive_mutation();
