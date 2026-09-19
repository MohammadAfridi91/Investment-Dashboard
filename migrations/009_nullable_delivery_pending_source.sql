-- ═══════════════════════════════════════════════════════════════════════════
-- 009_nullable_delivery_pending_source.sql
--
-- delivery_qty/delivery_pct were NOT NULL in 001, but the bulk delivery-
-- data report's URL isn't confirmed yet post-UDiFF (NSE discontinued the
-- old sec_bhavdata_full format on 2024-07-08; delivery data is no longer
-- bundled with the replacement UDiFF bhavcopy). Storing 0 as a placeholder
-- would look like real "zero delivery" data to every downstream percentile
-- and trend calculation. NULL is the honest representation of "not yet
-- available". Revert this (ADD NOT NULL back) once the real bulk source
-- is confirmed and wired into nse_bhavcopy.py.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE daily_prices ALTER COLUMN delivery_qty DROP NOT NULL;
ALTER TABLE daily_prices ALTER COLUMN delivery_pct DROP NOT NULL;
