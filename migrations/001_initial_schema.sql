CREATE TABLE IF NOT EXISTS universe (
    symbol VARCHAR(30) PRIMARY KEY,
    company_name TEXT NOT NULL,
    isin VARCHAR(20) UNIQUE NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    is_bfsi BOOLEAN DEFAULT FALSE,
    is_fno BOOLEAN DEFAULT FALSE,
    is_nifty500 BOOLEAN DEFAULT FALSE,
    is_midsmall400 BOOLEAN DEFAULT FALSE,
    listed_since DATE,
    raw_payload_checksum VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_prices (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    open_price NUMERIC NOT NULL,
    high_price NUMERIC NOT NULL,
    low_price NUMERIC NOT NULL,
    close_price NUMERIC NOT NULL,
    prev_close NUMERIC NOT NULL,
    adjusted_close NUMERIC NOT NULL,
    bhavcopy_avg_price NUMERIC NOT NULL,
    session_avg_price NUMERIC NOT NULL,
    volume BIGINT NOT NULL,
    delivery_qty BIGINT NOT NULL,
    delivery_pct NUMERIC NOT NULL,
    delivery_value NUMERIC,
    delivery_percentile_20d NUMERIC,
    delivery_trend_5d NUMERIC,
    traded_value NUMERIC NOT NULL,
    circuit_band NUMERIC DEFAULT 20.0,
    high_52w NUMERIC NOT NULL,
    low_52w NUMERIC NOT NULL,
    data_source VARCHAR(50) DEFAULT 'nse_bhavcopy',
    raw_payload_checksum VARCHAR(64),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS benchmark_prices (
    symbol VARCHAR(30) NOT NULL,
    trade_date DATE NOT NULL,
    close_price NUMERIC NOT NULL,
    volume BIGINT,
    raw_payload_checksum VARCHAR(64),
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS sector_indices (
    index_symbol VARCHAR(50) NOT NULL,
    trade_date DATE NOT NULL,
    close_price NUMERIC NOT NULL,
    raw_payload_checksum VARCHAR(64),
    PRIMARY KEY (index_symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS corporate_events (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    event_date DATE NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    purpose TEXT,
    is_sebi_regulatory BOOLEAN DEFAULT FALSE,
    source VARCHAR(50),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, event_date, event_type)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    ex_date DATE NOT NULL,
    record_date DATE,
    action_type VARCHAR(30) NOT NULL,
    ratio NUMERIC,
    face_value_change NUMERIC,
    dividend_amount NUMERIC,
    adjustment_factor NUMERIC NOT NULL,
    source VARCHAR(30) NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, ex_date, action_type)
);

CREATE TABLE IF NOT EXISTS derivative_metrics (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    fno_oi BIGINT NOT NULL,
    fno_oi_change BIGINT NOT NULL,
    prev_fno_oi BIGINT,
    cost_of_carry NUMERIC,
    prev_cost_of_carry NUMERIC,
    pcr NUMERIC,
    prev_pcr NUMERIC,
    oi_pcr_change NUMERIC,
    mwpl_pct NUMERIC,
    is_fno_ban BOOLEAN DEFAULT FALSE,
    has_institutional_net_buy BOOLEAN DEFAULT FALSE,
    rollover_pct NUMERIC,
    avg_rollover_pct_20d NUMERIC,
    basis NUMERIC,
    basis_pct NUMERIC,
    prev_basis_pct NUMERIC,
    iv_skew NUMERIC,
    max_pain NUMERIC,
    oi_concentration_top5 NUMERIC,
    spot_price NUMERIC,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS technical_indicators (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    ema_20 NUMERIC,
    ema_50 NUMERIC,
    sma_200 NUMERIC,
    atr_14 NUMERIC,
    atr_sma_20 NUMERIC,
    atr_compression BOOLEAN DEFAULT FALSE,
    mansfield_rs_500 NUMERIC,
    prev_mansfield_rs_500 NUMERIC,
    mansfield_rs_sector NUMERIC,
    prev_mansfield_rs_sector NUMERIC,
    avwap_swing_low NUMERIC,
    avwap_earnings NUMERIC,
    vpvr_hvn NUMERIC,
    vpvr_lvn NUMERIC,
    is_vpvr_breakout BOOLEAN DEFAULT FALSE,
    fractal_swing_low_20d NUMERIC NOT NULL,
    vpvr_hvn_levels JSONB,
    swing_high_levels_250d JSONB,
    swing_low_levels_250d JSONB,
    delivery_spike_ratio NUMERIC,
    adtv_20d NUMERIC,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS surveillance_registry (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    asm_stage INT DEFAULT 0,
    gsm_stage INT DEFAULT 0,
    is_t2t BOOLEAN DEFAULT FALSE,
    promoter_pledge_pct NUMERIC DEFAULT 0.0,
    pledge_rising_2q BOOLEAN DEFAULT FALSE,
    promoter_holding_pct NUMERIC,
    promoter_holding_change_4q NUMERIC,
    sast_sale_flag BOOLEAN DEFAULT FALSE,
    days_to_earnings INT DEFAULT 999,
    has_auditor_resignation BOOLEAN DEFAULT FALSE,
    has_regulatory_raid BOOLEAN DEFAULT FALSE,
    has_forensic_audit BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (symbol, record_date)
);

CREATE TABLE IF NOT EXISTS auditor_history (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    fiscal_year INT NOT NULL,
    auditor_firm TEXT NOT NULL,
    is_tier1 BOOLEAN DEFAULT FALSE,
    mid_term_resignation BOOLEAN DEFAULT FALSE,
    resignation_date DATE,
    has_qualified_opinion BOOLEAN DEFAULT FALSE,
    qualification_notes TEXT,
    caro_qualified BOOLEAN DEFAULT FALSE,
    non_audit_fee_ratio NUMERIC,
    PRIMARY KEY (symbol, fiscal_year)
);

CREATE TABLE IF NOT EXISTS forensic_financials (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    fiscal_year INT NOT NULL,
    sector VARCHAR(100),
    sales NUMERIC, cogs NUMERIC, sga_expense NUMERIC, ebitda NUMERIC,
    depreciation NUMERIC, ebit NUMERIC, interest_expense NUMERIC,
    tax_rate NUMERIC, nopat NUMERIC, net_profit NUMERIC, other_income NUMERIC,
    cfo NUMERIC, capex NUMERIC, fcf NUMERIC, principal_repayment NUMERIC,
    gross_block NUMERIC, cwip NUMERIC, net_block NUMERIC,
    total_assets NUMERIC, current_assets NUMERIC, current_liabilities NUMERIC,
    receivables NUMERIC, inventory NUMERIC, trade_payables NUMERIC,
    cash_and_equivalents NUMERIC, net_worth NUMERIC, total_debt NUMERIC,
    total_liabilities NUMERIC, net_debt NUMERIC, shares_outstanding NUMERIC,
    contingent_liabilities NUMERIC, market_cap NUMERIC, enterprise_value NUMERIC,
    capital_employed NUMERIC, roce NUMERIC, roce_5y_avg NUMERIC,
    roce_wacc_spread NUMERIC, roic_5y_avg NUMERIC, roiic_5y NUMERIC,
    wacc NUMERIC, gross_debt_to_ebitda NUMERIC, net_debt_to_ebitda NUMERIC,
    interest_coverage NUMERIC, dscr NUMERIC, beneish_m_score NUMERIC,
    altman_z_double_prime NUMERIC, piotroski_f_score INT, sloan_accrual NUMERIC,
    cfo_to_ebitda_5y NUMERIC, cfo_to_pat NUMERIC, fcf_years_positive INT,
    gross_margin_stable BOOLEAN DEFAULT TRUE, cash_conversion_cycle NUMERIC,
    receivable_days NUMERIC, inventory_days NUMERIC, payable_days NUMERIC,
    fixed_asset_turnover NUMERIC, capex_to_depreciation NUMERIC,
    capacity_utilization_pass BOOLEAN DEFAULT TRUE,
    implied_dcf_growth NUMERIC, implied_dcf_growth_bear NUMERIC,
    implied_dcf_growth_base NUMERIC, implied_dcf_growth_bull NUMERIC,
    fcf_yield NUMERIC, has_rpt_siphoning BOOLEAN DEFAULT FALSE,
    esop_dilution_annual NUMERIC, effective_date DATE, announcement_date DATE,
    restatement_flag BOOLEAN DEFAULT FALSE, consolidated_flag BOOLEAN DEFAULT TRUE,
    accounting_standard VARCHAR(20), data_source VARCHAR(50),
    ingested_at TIMESTAMPTZ DEFAULT NOW(), source_checksum VARCHAR(64),
    PRIMARY KEY (symbol, fiscal_year)
);

CREATE TABLE IF NOT EXISTS institutional_deals (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    deal_date DATE NOT NULL,
    deal_type VARCHAR(10) NOT NULL,
    client_name TEXT NOT NULL,
    normalized_client_name TEXT,
    pan VARCHAR(10),
    trade_direction VARCHAR(4) NOT NULL,
    quantity BIGINT NOT NULL,
    price NUMERIC NOT NULL,
    is_institutional BOOLEAN DEFAULT FALSE,
    is_wash_trade BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (symbol, deal_date, client_name, trade_direction, deal_type)
);

CREATE TABLE IF NOT EXISTS market_regime (
    trade_date DATE PRIMARY KEY,
    india_vix NUMERIC,
    nifty_500_close NUMERIC,
    nifty_500_sma_50 NUMERIC,
    nifty_500_sma_200 NUMERIC,
    nifty_trend VARCHAR(20),
    market_breadth NUMERIC,
    fii_cash_net_cr NUMERIC,
    dii_cash_net_cr NUMERIC,
    usdinr NUMERIC,
    brent_crude NUMERIC,
    us10y NUMERIC,
    gsec_10y_yield NUMERIC,
    regime_classification VARCHAR(20),
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance_events (
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    event_date DATE NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20),
    details TEXT,
    source VARCHAR(50) NOT NULL,
    source_url TEXT,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, event_date, event_type)
);

CREATE TABLE IF NOT EXISTS trade_check_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(30) REFERENCES universe(symbol) ON DELETE CASCADE,
    desk_type VARCHAR(20) NOT NULL,
    eval_date DATE NOT NULL,
    hard_gates_pass BOOLEAN NOT NULL,
    score NUMERIC NOT NULL,
    max_score NUMERIC NOT NULL,
    verdict VARCHAR(30) NOT NULL,
    entry_trigger NUMERIC, stop_loss NUMERIC,
    target_1 NUMERIC, target_2 NUMERIC,
    risk_reward_ratio NUMERIC, position_size_shares INT, valid_until DATE,
    card_details JSONB NOT NULL,
    sebi_disclosure_snapshot JSONB,
    restatement_caution BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sebi_compliance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(30), card_id UUID, actor VARCHAR(50),
    payload JSONB NOT NULL, rationale TEXT, disclosure_text TEXT,
    retention_until DATE NOT NULL, checksum VARCHAR(64) NOT NULL
);
