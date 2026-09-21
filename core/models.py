from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class UniverseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    company_name: str
    isin: str
    sector: str | None = None
    industry: str | None = None
    is_bfsi: bool = False
    is_fno: bool = False
    is_nifty500: bool = False
    is_midsmall400: bool = False
    listed_since: date | None = None
    raw_payload_checksum: str | None = None

class DailyPriceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    prev_close: float
    adjusted_close: float
    bhavcopy_avg_price: float
    session_avg_price: float
    volume: int
    delivery_qty: int
    delivery_pct: float
    delivery_value: float | None = None
    delivery_percentile_20d: float | None = None
    delivery_trend_5d: float | None = None
    traded_value: float
    circuit_band: float = 20.0
    high_52w: float
    low_52w: float
    data_source: str = "nse_bhavcopy"
    raw_payload_checksum: str | None = None

class BenchmarkPriceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    trade_date: date
    close_price: float
    volume: int | None = None
    raw_payload_checksum: str | None = None

class SectorIndexRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    index_symbol: str
    trade_date: date
    close_price: float
    raw_payload_checksum: str | None = None

class MarketRegimeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    trade_date: date
    india_vix: float | None = None
    nifty_500_close: float | None = None
    nifty_500_sma_50: float | None = None
    nifty_500_sma_200: float | None = None
    nifty_trend: str | None = None
    market_breadth: float | None = None
    fii_cash_net_cr: float | None = None
    dii_cash_net_cr: float | None = None
    usdinr: float | None = None
    brent_crude: float | None = None
    us10y: float | None = None
    gsec_10y_yield: float | None = None
    regime_classification: str | None = None

class PipelineHealthRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    workflow: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    rows_processed: int | None = None
    error_message: str | None = None


class DerivativeMetricsRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    trade_date: date
    fno_oi: int
    fno_oi_change: int
    prev_fno_oi: int | None = None
    cost_of_carry: float | None = None
    prev_cost_of_carry: float | None = None
    pcr: float | None = None
    prev_pcr: float | None = None
    oi_pcr_change: float | None = None
    mwpl_pct: float | None = None
    is_fno_ban: bool = False
    has_institutional_net_buy: bool = False
    rollover_pct: float | None = None
    avg_rollover_pct_20d: float | None = None
    basis: float | None = None
    basis_pct: float | None = None
    prev_basis_pct: float | None = None
    iv_skew: float | None = None
    max_pain: float | None = None
    oi_concentration_top5: float | None = None
    spot_price: float | None = None


class SurveillanceRegistryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    record_date: date
    asm_stage: int = 0
    gsm_stage: int = 0
    is_t2t: bool = False
    promoter_pledge_pct: float = 0.0
    pledge_rising_2q: bool = False
    promoter_holding_pct: float | None = None
    promoter_holding_change_4q: float | None = None
    sast_sale_flag: bool = False
    days_to_earnings: int = 999
    has_auditor_resignation: bool = False
    has_regulatory_raid: bool = False
    has_forensic_audit: bool = False


class InstitutionalDealRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    deal_date: date
    deal_type: str
    client_name: str
    normalized_client_name: str | None = None
    pan: str | None = None
    trade_direction: str
    quantity: int
    price: float
    is_institutional: bool = False
    is_wash_trade: bool = False


class CorporateActionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    ex_date: date
    record_date: date | None = None
    action_type: str
    ratio: float | None = None
    face_value_change: float | None = None
    dividend_amount: float | None = None
    adjustment_factor: float = 1.0
    source: str = "nse_actions_csv"


class AuditorHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    fiscal_year: int
    auditor_firm: str
    is_tier1: bool = False
    mid_term_resignation: bool = False
    resignation_date: date | None = None
    has_qualified_opinion: bool = False
    qualification_notes: str | None = None
    caro_qualified: bool = False
    non_audit_fee_ratio: float | None = None


class GovernanceEventRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    event_date: date
    event_type: str
    severity: str | None = None
    details: str | None = None
    source: str = "bse_api"
    source_url: str | None = None
    ingested_at: datetime | None = None


class ForensicFinancialsRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    fiscal_year: int
    sector: str | None = None
    sales: float | None = None
    cogs: float | None = None
    sga_expense: float | None = None
    ebitda: float | None = None
    depreciation: float | None = None
    ebit: float | None = None
    interest_expense: float | None = None
    tax_rate: float | None = None
    nopat: float | None = None
    net_profit: float | None = None
    other_income: float | None = None
    cfo: float | None = None
    capex: float | None = None
    fcf: float | None = None
    principal_repayment: float | None = None
    gross_block: float | None = None
    cwip: float | None = None
    net_block: float | None = None
    total_assets: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    receivables: float | None = None
    inventory: float | None = None
    trade_payables: float | None = None
    cash_and_equivalents: float | None = None
    net_worth: float | None = None
    total_debt: float | None = None
    total_liabilities: float | None = None
    net_debt: float | None = None
    shares_outstanding: float | None = None
    contingent_liabilities: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    capital_employed: float | None = None
    roce: float | None = None
    roce_5y_avg: float | None = None
    roce_wacc_spread: float | None = None
    roic_5y_avg: float | None = None
    roiic_5y: float | None = None
    wacc: float | None = None
    gross_debt_to_ebitda: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    dscr: float | None = None
    beneish_m_score: float | None = None
    altman_z_double_prime: float | None = None
    piotroski_f_score: int | None = None
    sloan_accrual: float | None = None
    cfo_to_ebitda_5y: float | None = None
    cfo_to_pat: float | None = None
    fcf_years_positive: int | None = None
    gross_margin_stable: bool = True
    cash_conversion_cycle: float | None = None
    receivable_days: float | None = None
    inventory_days: float | None = None
    payable_days: float | None = None
    fixed_asset_turnover: float | None = None
    capex_to_depreciation: float | None = None
    capacity_utilization_pass: bool = True
    implied_dcf_growth: float | None = None
    implied_dcf_growth_bear: float | None = None
    implied_dcf_growth_base: float | None = None
    implied_dcf_growth_bull: float | None = None
    fcf_yield: float | None = None
    has_rpt_siphoning: bool = False
    esop_dilution_annual: float | None = None
    effective_date: date | None = None
    announcement_date: date | None = None
    restatement_flag: bool = False
    consolidated_flag: bool = True
    accounting_standard: str | None = None
    data_source: str = "screener"
    ingested_at: datetime | None = None
    source_checksum: str | None = None


