"""Local terminal interactive quick-lookup utility for Dalal Street Automation Engine v6.5."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from core.alerts.formatters import (
    format_card1_ascii,
    format_card1_markdown,
    format_card2_ascii,
    format_card2_markdown,
    format_regime_markdown,
)
from core.config import load_config
from core.database.client import DB
from core.engines.strategic_desk import StrategicDesk
from core.engines.tactical_desk import TacticalDesk
from core.models import MarketRegimeRow


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dalal Street Engine v6.5 Interactive Terminal Inspector",
    )
    parser.add_argument(
        "--symbol",
        "-s",
        type=str,
        help="Stock ticker symbol (e.g. TCS, INFY, RELIANCE)",
    )
    parser.add_argument(
        "--desk",
        "-d",
        choices=["tactical", "strategic", "both"],
        default="both",
        help="Which desk card to evaluate (default: both)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Evaluation date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--regime",
        "-r",
        action="store_true",
        help="Display current Macro Market Regime status",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan universe for top setups and tier 1/2 candidates",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["ascii", "markdown"],
        default="ascii",
        help="Card display format (default: ascii)",
    )
    return parser.parse_args(args)


def run_cli(args: argparse.Namespace) -> int:
    cfg = load_config()
    db = DB.from_env()

    eval_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()

    # 1. Macro Regime Check
    if args.regime:
        rows = db.select("market_regime", order="trade_date.desc", limit=1)
        if not rows:
            print("⚠️ No market regime records found in database.")
        else:
            regime = MarketRegimeRow.model_validate(rows[0])
            print(format_regime_markdown(regime))
        if not args.symbol and not args.scan:
            return 0

    # 2. Universe Scan Mode
    if args.scan:
        print(f"\n🔍 Scanning Universe for Evaluation Date: {eval_date}...")
        tactical = TacticalDesk(db, cfg)
        strategic = StrategicDesk(db, cfg)

        fno_stocks = db.select(
            "universe",
            columns="symbol",
            filters={"is_fno": True, "is_bfsi": False},
            limit=20,
        )
        print(f"\n--- TACTICAL SWING CANDIDATES (Top {len(fno_stocks)} F&O) ---")
        for s in fno_stocks:
            sym = s.get("symbol")
            if not sym:
                continue
            card1 = tactical.evaluate_from_db(sym, eval_date)
            if card1:
                status = "✅ EXECUTE" if card1.verdict == "EXECUTE" else "❌ ABORT"
                print(
                    f"[{sym:<10}] {status:<10} Score: {card1.score:.1f}/{card1.max_score:.1f} | Gates: {'PASS' if card1.hard_gates_pass else 'FAIL'}"
                )

        strat_stocks = db.select(
            "universe",
            columns="symbol",
            filters={"is_nifty500": True, "is_bfsi": False},
            limit=20,
        )
        print(f"\n--- STRATEGIC CORE CANDIDATES (Top {len(strat_stocks)} Non-BFSI) ---")
        for s in strat_stocks:
            sym = s.get("symbol")
            if not sym:
                continue
            card2 = strategic.evaluate_from_db(sym, eval_date)
            if card2:
                print(
                    f"[{sym:<10}] Verdict: {card2.verdict:<10} Score: {card2.score:.1f}/{card2.max_score:.1f} | Forensic: {'PASS' if card2.hard_gates_pass else 'FAIL'}"
                )
        return 0

    # 3. Single Stock Evaluation
    if not args.symbol:
        print("Error: Please specify --symbol SYMBOL, --scan, or --regime. Use --help for usage.")
        return 1

    sym = args.symbol.upper().strip()
    fmt = args.format

    # Evaluate Tactical Card
    if args.desk in ["tactical", "both"]:
        tactical = TacticalDesk(db, cfg)
        card1 = tactical.evaluate_from_db(sym, eval_date)
        if not card1:
            print(f"⚠️ Tactical evaluation unavailable for {sym} on {eval_date}.")
        else:
            out = format_card1_ascii(card1) if fmt == "ascii" else format_card1_markdown(card1)
            print("\n" + out)

    # Evaluate Strategic Card
    if args.desk in ["strategic", "both"]:
        strategic = StrategicDesk(db, cfg)
        card2 = strategic.evaluate_from_db(sym, eval_date)
        if not card2:
            print(f"⚠️ Strategic evaluation unavailable for {sym} on {eval_date}.")
        else:
            out = format_card2_ascii(card2) if fmt == "ascii" else format_card2_markdown(card2)
            print("\n" + out)

    return 0


def main() -> None:
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
