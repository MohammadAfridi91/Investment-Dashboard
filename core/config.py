from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Card1Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adtv_min_inr: int
    mwpl_max_pct: float
    pcr_band: tuple[float, float]
    delivery_value_percentile_min: int
    atr_compression_ratio: float
    rs_lookback_days: int
    rr_min: float
    score_min_risk_on: int
    score_min_neutral: int
    score_min_risk_off: int
    oi_buildup_min_pct: float
    active_confirmations_required: int
    gap_atr_multiplier_max: float
    pcr_rising_required: bool
    coc_requires_price_oi: bool
    price_min: float = 20.0


class Card2Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier1_min: int
    tier2_min: int
    roic_wacc_spread_min: float
    roce_wacc_spread_min: float = 0.05
    roiic_min: float
    fcf_positive_years_min: int
    gm_decline_tolerance: float
    nd_ebitda_max: float
    interest_coverage_min: float
    altman_z_min: float
    piotroski_f_min: int
    sloan_accrual_max: float
    cfo_pat_min: float
    esop_dilution_max: float
    cwip_max_card2: float
    pledge_max_card2: float
    obs_max: float
    dscr_min: float
    adtv_min_inr: int
    market_cap_min_inr: int
    promoter_holding_decline_max: float


class FatalConfig(BaseModel):
    pledge_max_pct: float
    cwip_max_pct: float
    cwip_consecutive_years: int
    royalty_max_pct_of_revenue: float
    asm_min_stage_kill: int
    gsm_min_stage_kill: int


class WaccConfig(BaseModel):
    erp: float
    beta_band: tuple[float, float]
    beta_lookback_years: int
    beta_benchmark: str
    kd_zero_debt_fallback_spread: float
    kd_zero_debt_tax_rate: float


class DcfConfig(BaseModel):
    years: int
    g_term: float
    brent_tol: float
    brent_bounds: tuple[float, float]


class InstitutionalRegex(BaseModel):
    amc: str
    insurance: str
    fii: str


class WashTradeConfig(BaseModel):
    qty_match_pct: float
    min_value_inr: int


class MarketRegimeConfig(BaseModel):
    vix_risk_off: float
    breadth_risk_off: float
    vix_risk_on: float = 15.0
    breadth_risk_on: float = 0.60
    india_vix_source: str
    fii_dii_source: str


class SectorRsConfig(BaseModel):
    mapping_file: str
    fallback: str


class PitConfig(BaseModel):
    mode: str
    backfill_years: int
    price_backfill_sessions: int


class ComplianceConfig(BaseModel):
    sebi_ra_registered: bool
    report_retention_years: int
    immutable_archive_dir: str
    no_guaranteed_return_language: bool
    upsi_logging: bool


class VendorLicenseConfig(BaseModel):
    mode: str
    redistribution_allowed: bool


class IngestionConfig(BaseModel):
    request_delay_nse_archives_ms: int
    request_delay_nse_api_ms: int
    request_delay_bse_api_ms: int
    request_delay_screener_ms: int
    retry_attempts: int
    retry_backoff_seconds: list[int]
    user_agent: str
    backfill_sessions: int = 375
    high_52w_window_sessions: int = 252
    screener_robots_check: bool = True


class Holiday(BaseModel):
    date: date
    name: str


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portfolio_capital: int
    card1: Card1Config
    card1_active_confirmations: list[str] = Field(default_factory=list)
    card2: Card2Config
    fatal: FatalConfig
    wacc: WaccConfig
    dcf: DcfConfig
    sector_tam_growth: dict[str, float]
    tier1_auditors: list[str]
    institutional_regex: InstitutionalRegex
    wash_trade: WashTradeConfig
    market_regime: MarketRegimeConfig
    sector_rs: SectorRsConfig
    pit: PitConfig
    compliance: ComplianceConfig
    vendor_license: VendorLicenseConfig
    ingestion: IngestionConfig
    governance_fatal: list[str]
    RISK_OFF_SCORE_THRESHOLD: int = 99
    nse_holidays_file: str = "config/nse_holidays.json"
    industry_mappings_file: str = "config/industry_mappings.json"
    nse_holidays: list[Holiday] = Field(default_factory=list)

    def is_holiday(self, d: date) -> bool:
        return any(h.date == d for h in self.nse_holidays)


def load_config(
    yaml_path: str | Path = "config/config.yaml",
    holidays_path: str | Path = "config/nse_holidays.json",
    year: int | None = None,
) -> Config:
    yp = Path(yaml_path)
    hp = Path(holidays_path)
    with yp.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    with hp.open("r", encoding="utf-8") as f:
        hol_raw: dict[str, list[dict[str, str]]] = json.load(f)
    yr = year or date.today().year
    holidays = [
        Holiday(date=date.fromisoformat(h["date"]), name=h["name"])
        for h in hol_raw.get(str(yr), [])
    ]
    cfg = Config(**raw)
    cfg.nse_holidays = holidays
    return cfg
