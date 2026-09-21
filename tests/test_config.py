from datetime import date

from core.config import load_config


def test_load_config_default():
    cfg = load_config()
    assert cfg.portfolio_capital == 5_000_000
    assert cfg.card1.score_min_risk_on == 8
    assert cfg.card1.score_min_risk_off == 99
    assert cfg.card2.altman_z_min == 2.6
    assert cfg.ingestion.high_52w_window_sessions == 252
    assert cfg.pit.price_backfill_sessions == 375
    assert cfg.RISK_OFF_SCORE_THRESHOLD == 99

def test_nse_holidays_loaded():
    cfg = load_config(year=2026)
    assert len(cfg.nse_holidays) > 0
    assert cfg.is_holiday(date(2026, 1, 26))
    assert not cfg.is_holiday(date(2026, 1, 27))

def test_no_flat_card1_keys():
    cfg = load_config()
    assert hasattr(cfg, "card1")
    assert not hasattr(cfg, "card1_score_min_neutral")
