ALTER TABLE derivative_metrics
    ADD COLUMN IF NOT EXISTS prev_pcr NUMERIC;
ALTER TABLE market_regime
    ADD COLUMN IF NOT EXISTS gsec_10y_yield NUMERIC;
