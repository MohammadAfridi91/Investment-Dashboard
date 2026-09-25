from __future__ import annotations

from typing import Any


def _val(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def evaluate_fatal_red_flags(
    symbol: str,
    surv: Any,
    fin_3y: list[Any],
    auditor_3y: list[Any],
) -> dict[str, Any]:
    """Evaluate Layer 2 fatal red flags across 5 critical corporate governance/structural gates.

    Returns dict with:
        'passed': bool (True if zero fatal flags triggered)
        'flags': dict[str, bool]
        'failed_gates': list[str]
    """
    flags: dict[str, bool] = {}

    # 1. Promoter pledge fatal gate (>20% or rising for 2 consecutive quarters)
    pledge_pct = _val(surv, "promoter_pledge_pct", 0.0) or 0.0
    pledge_rising = bool(_val(surv, "pledge_rising_2q", False))
    flags["pledge_fatal"] = pledge_pct > 20.0 or pledge_rising

    # 2. Auditor mid-term resignation in trailing 3 fiscal years
    flags["auditor_escape"] = any(bool(_val(a, "mid_term_resignation", False)) for a in auditor_3y)

    # 3. Capital Work-in-Progress (CWIP) parking (>50% of gross block for 3 consecutive years)
    cwip_ratios: list[float] = []
    for f in fin_3y:
        gb = _val(f, "gross_block", 0.0) or 0.0
        cw = _val(f, "cwip", 0.0) or 0.0
        if gb > 0:
            cwip_ratios.append(cw / gb)

    flags["cwip_parking"] = len(cwip_ratios) >= 3 and all(r > 0.50 for r in cwip_ratios[-3:])

    # 4. Related Party Transactions (RPT) siphoning
    flags["rpt_siphoning"] = any(bool(_val(f, "has_rpt_siphoning", False)) for f in fin_3y)

    # 5. Regulatory seizure (ASM >= 2, GSM >= 1, T2T, raids, or forensic audit)
    asm_stage = _val(surv, "asm_stage", 0) or 0
    gsm_stage = _val(surv, "gsm_stage", 0) or 0
    is_t2t = bool(_val(surv, "is_t2t", False))
    has_raid = bool(_val(surv, "has_regulatory_raid", False))
    has_forensic = bool(_val(surv, "has_forensic_audit", False))

    flags["regulatory_seizure"] = (
        asm_stage >= 2 or gsm_stage >= 1 or is_t2t or has_raid or has_forensic
    )

    is_fatal = any(flags.values())
    failed = [k for k, v in flags.items() if v]

    return {
        "passed": not is_fatal,
        "flags": flags,
        "failed_gates": failed if is_fatal else [],
    }
