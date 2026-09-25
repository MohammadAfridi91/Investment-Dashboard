"""Tests for interactive_cli.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from interactive_cli import parse_args, run_cli


def test_cli_argument_parsing() -> None:
    args = parse_args(["--symbol", "TCS", "--desk", "tactical", "--format", "markdown"])
    assert args.symbol == "TCS"
    assert args.desk == "tactical"
    assert args.format == "markdown"
    assert args.regime is False
    assert args.scan is False


def test_cli_missing_symbol_and_flags_returns_1() -> None:
    args = parse_args([])
    with patch("core.config.load_config"), patch("core.database.client.DB.from_env"):
        code = run_cli(args)
        assert code == 1


def test_cli_regime_flag() -> None:
    args = parse_args(["--regime"])
    mock_db = MagicMock()
    mock_db.select.return_value = [
        {
            "trade_date": "2026-09-25",
            "india_vix": 12.0,
            "regime_classification": "RISK_ON",
        }
    ]

    with (
        patch("core.config.load_config"),
        patch("core.database.client.DB.from_env", return_value=mock_db),
    ):
        code = run_cli(args)
        assert code == 0


def test_cli_single_symbol_tactical_and_strategic() -> None:
    args = parse_args(["--symbol", "TCS", "--desk", "both", "--format", "ascii"])
    mock_db = MagicMock()

    mock_card1 = MagicMock()
    mock_card1.symbol = "TCS"
    mock_card1.eval_date = date(2026, 9, 25)
    mock_card1.verdict = "EXECUTE"
    mock_card1.score = 9.0
    mock_card1.max_score = 10.0
    mock_card1.hard_gates_pass = True
    mock_card1.valid_until = date(2026, 9, 26)
    mock_card1.entry_trigger = 3850.0
    mock_card1.stop_loss = 3780.0
    mock_card1.target_1 = 3950.0
    mock_card1.target_2 = 4100.0
    mock_card1.risk_reward_ratio = 2.85
    mock_card1.position_size_shares = 120
    mock_card1.card_details = {}

    mock_card2 = MagicMock()
    mock_card2.symbol = "TCS"
    mock_card2.eval_date = date(2026, 9, 25)
    mock_card2.verdict = "TIER_1"
    mock_card2.score = 44.0
    mock_card2.max_score = 50.0
    mock_card2.hard_gates_pass = True
    mock_card2.restatement_caution = False
    mock_card2.card_details = {
        "moat_score": {"total": 25},
        "sector_score": {"total": 10},
        "valuation_score": {"total": 9},
    }

    with (
        patch("core.config.load_config"),
        patch("core.database.client.DB.from_env", return_value=mock_db),
        patch("interactive_cli.TacticalDesk.evaluate_from_db", return_value=mock_card1),
        patch("interactive_cli.StrategicDesk.evaluate_from_db", return_value=mock_card2),
    ):
        code = run_cli(args)
        assert code == 0


def test_cli_scan_flag() -> None:
    args = parse_args(["--scan"])
    mock_db = MagicMock()
    mock_db.select.side_effect = [
        [{"symbol": "TCS"}, {"symbol": "INFY"}],
        [{"symbol": "TCS"}, {"symbol": "INFY"}],
    ]

    with (
        patch("core.config.load_config"),
        patch("core.database.client.DB.from_env", return_value=mock_db),
        patch("interactive_cli.TacticalDesk.evaluate_from_db", return_value=None),
        patch("interactive_cli.StrategicDesk.evaluate_from_db", return_value=None),
    ):
        code = run_cli(args)
        assert code == 0
