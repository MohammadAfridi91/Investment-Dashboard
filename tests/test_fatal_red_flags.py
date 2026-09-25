from __future__ import annotations

from core.filters.fatal_red_flags import evaluate_fatal_red_flags
from core.models import (
    AuditorHistoryRow,
    ForensicFinancialsRow,
    SurveillanceRegistryRow,
)


def test_fatal_red_flags_clean_firm() -> None:
    surv = SurveillanceRegistryRow(
        symbol="TCS",
        record_date="2024-03-31",  # type: ignore[arg-type]
        asm_stage=0,
        gsm_stage=0,
        is_t2t=False,
        promoter_pledge_pct=0.0,
        pledge_rising_2q=False,
        has_regulatory_raid=False,
        has_forensic_audit=False,
    )
    fin_3y = [
        ForensicFinancialsRow(
            symbol="TCS", fiscal_year=2022, gross_block=1000.0, cwip=50.0, has_rpt_siphoning=False
        ),
        ForensicFinancialsRow(
            symbol="TCS", fiscal_year=2023, gross_block=1100.0, cwip=60.0, has_rpt_siphoning=False
        ),
        ForensicFinancialsRow(
            symbol="TCS", fiscal_year=2024, gross_block=1200.0, cwip=70.0, has_rpt_siphoning=False
        ),
    ]
    auditor_3y = [
        AuditorHistoryRow(
            symbol="TCS", fiscal_year=2022, auditor_firm="BSR & Co", mid_term_resignation=False
        ),
        AuditorHistoryRow(
            symbol="TCS", fiscal_year=2023, auditor_firm="BSR & Co", mid_term_resignation=False
        ),
        AuditorHistoryRow(
            symbol="TCS", fiscal_year=2024, auditor_firm="BSR & Co", mid_term_resignation=False
        ),
    ]

    res = evaluate_fatal_red_flags("TCS", surv, fin_3y, auditor_3y)
    assert res["passed"] is True
    assert res["failed_gates"] == []
    for flag_val in res["flags"].values():
        assert flag_val is False


def test_fatal_red_flags_historical_regressions() -> None:
    """Verification Plan Test 1: Brightcom, Cox & Kings, Sintex, DHFL trigger 100% of expected gates."""
    # 1. Brightcom Group: Regulatory raid, forensic audit, auditor escape
    surv_bcg = {
        "promoter_pledge_pct": 5.0,
        "pledge_rising_2q": False,
        "asm_stage": 2,
        "gsm_stage": 0,
        "is_t2t": False,
        "has_regulatory_raid": True,
        "has_forensic_audit": True,
    }
    fin_bcg = [
        {"gross_block": 500.0, "cwip": 100.0, "has_rpt_siphoning": False},
        {"gross_block": 550.0, "cwip": 110.0, "has_rpt_siphoning": False},
        {"gross_block": 600.0, "cwip": 120.0, "has_rpt_siphoning": False},
    ]
    aud_bcg = [
        {"mid_term_resignation": True, "auditor_firm": "PwC"},
    ]
    res_bcg = evaluate_fatal_red_flags("BCG", surv_bcg, fin_bcg, aud_bcg)
    assert res_bcg["passed"] is False
    assert "regulatory_seizure" in res_bcg["failed_gates"]
    assert "auditor_escape" in res_bcg["failed_gates"]

    # 2. Cox & Kings: Mid-term auditor resignation and forensic audit
    surv_ck = {
        "promoter_pledge_pct": 12.0,
        "pledge_rising_2q": False,
        "asm_stage": 1,
        "gsm_stage": 0,
        "is_t2t": False,
        "has_regulatory_raid": False,
        "has_forensic_audit": True,
    }
    fin_ck = [
        {"gross_block": 800.0, "cwip": 80.0, "has_rpt_siphoning": False},
        {"gross_block": 800.0, "cwip": 90.0, "has_rpt_siphoning": False},
        {"gross_block": 800.0, "cwip": 100.0, "has_rpt_siphoning": False},
    ]
    aud_ck = [
        {"mid_term_resignation": True, "auditor_firm": "DTL"},
    ]
    res_ck = evaluate_fatal_red_flags("COX&KINGS", surv_ck, fin_ck, aud_ck)
    assert res_ck["passed"] is False
    assert "auditor_escape" in res_ck["failed_gates"]
    assert "regulatory_seizure" in res_ck["failed_gates"]

    # 3. Sintex Industries: Extreme pledge (>20%) and massive CWIP parking (>50% for 3 yrs)
    surv_sintex = {
        "promoter_pledge_pct": 48.5,
        "pledge_rising_2q": True,
        "asm_stage": 0,
        "gsm_stage": 0,
        "is_t2t": False,
        "has_regulatory_raid": False,
        "has_forensic_audit": False,
    }
    fin_sintex = [
        {"gross_block": 1000.0, "cwip": 650.0, "has_rpt_siphoning": False},  # 65%
        {"gross_block": 1100.0, "cwip": 700.0, "has_rpt_siphoning": False},  # 63.6%
        {"gross_block": 1200.0, "cwip": 750.0, "has_rpt_siphoning": False},  # 62.5%
    ]
    aud_sintex = [
        {"mid_term_resignation": False},
        {"mid_term_resignation": False},
        {"mid_term_resignation": False},
    ]
    res_sintex = evaluate_fatal_red_flags("SINTEX", surv_sintex, fin_sintex, aud_sintex)
    assert res_sintex["passed"] is False
    assert "pledge_fatal" in res_sintex["failed_gates"]
    assert "cwip_parking" in res_sintex["failed_gates"]

    # 4. DHFL: RPT siphoning and regulatory raid/action
    surv_dhfl = {
        "promoter_pledge_pct": 15.0,
        "pledge_rising_2q": False,
        "asm_stage": 0,
        "gsm_stage": 0,
        "is_t2t": False,
        "has_regulatory_raid": True,
        "has_forensic_audit": False,
    }
    fin_dhfl = [
        {"gross_block": 500.0, "cwip": 20.0, "has_rpt_siphoning": True},
        {"gross_block": 520.0, "cwip": 25.0, "has_rpt_siphoning": False},
        {"gross_block": 530.0, "cwip": 30.0, "has_rpt_siphoning": False},
    ]
    aud_dhfl = [
        {"mid_term_resignation": False},
    ]
    res_dhfl = evaluate_fatal_red_flags("DHFL", surv_dhfl, fin_dhfl, aud_dhfl)
    assert res_dhfl["passed"] is False
    assert "rpt_siphoning" in res_dhfl["failed_gates"]
    assert "regulatory_seizure" in res_dhfl["failed_gates"]


def test_fatal_red_flags_individual_gates() -> None:
    base_surv = {
        "promoter_pledge_pct": 0.0,
        "pledge_rising_2q": False,
        "asm_stage": 0,
        "gsm_stage": 0,
    }
    base_fin = [{"gross_block": 100.0, "cwip": 10.0}] * 3
    base_aud: list[dict[str, bool]] = []

    # Pledge rising alone
    s1 = dict(base_surv, pledge_rising_2q=True)
    r1 = evaluate_fatal_red_flags("SYM1", s1, base_fin, base_aud)
    assert r1["passed"] is False
    assert r1["failed_gates"] == ["pledge_fatal"]

    # CWIP high for 2 years only -> does NOT trigger cwip_parking
    fin_2yr_cwip = [
        {"gross_block": 100.0, "cwip": 20.0},
        {"gross_block": 100.0, "cwip": 60.0},
        {"gross_block": 100.0, "cwip": 70.0},
    ]
    r2 = evaluate_fatal_red_flags("SYM2", base_surv, fin_2yr_cwip, base_aud)
    assert r2["passed"] is True
    assert "cwip_parking" not in r2["failed_gates"]

    # GSM stage >= 1 triggers regulatory seizure
    s3 = dict(base_surv, gsm_stage=1)
    r3 = evaluate_fatal_red_flags("SYM3", s3, base_fin, base_aud)
    assert r3["passed"] is False
    assert r3["failed_gates"] == ["regulatory_seizure"]

    # T2T triggers regulatory seizure
    s4 = dict(base_surv, is_t2t=True)
    r4 = evaluate_fatal_red_flags("SYM4", s4, base_fin, base_aud)
    assert r4["passed"] is False
    assert r4["failed_gates"] == ["regulatory_seizure"]
