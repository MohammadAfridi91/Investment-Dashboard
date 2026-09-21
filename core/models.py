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

