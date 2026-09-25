"""Tests for TelegramNotifier."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from core.alerts.telegram_bot import TelegramNotifier
from core.models import MarketRegimeRow, TradeCheckCardRow


def test_telegram_unconfigured_graceful_false() -> None:
    notifier = TelegramNotifier(bot_token=None, chat_id=None)
    assert not notifier.is_configured
    assert notifier.send_message("Test message") is False


def test_telegram_send_success() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    assert notifier.is_configured

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = notifier.send_message("Hello Dalal Street")
        assert success is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.telegram.org/bottest_token/sendMessage"
        assert kwargs["json"]["chat_id"] == "12345"
        assert kwargs["json"]["text"] == "Hello Dalal Street"


def test_telegram_send_failure_status() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request: chat not found"

    with patch("requests.post", return_value=mock_resp):
        success = notifier.send_message("Test message")
        assert success is False


def test_telegram_send_transport_exception() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")

    with patch("requests.post", side_effect=Exception("Connection timed out")):
        success = notifier.send_message("Test message")
        assert success is False


def test_telegram_send_cards_and_regime() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    card1 = TradeCheckCardRow(
        symbol="TATASTEEL",
        desk_type="TACTICAL",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=9.0,
        max_score=10.0,
        verdict="EXECUTE",
        entry_trigger=155.0,
    )
    card2 = TradeCheckCardRow(
        symbol="TCS",
        desk_type="STRATEGIC",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=45.0,
        max_score=50.0,
        verdict="TIER_1",
    )
    regime = MarketRegimeRow(
        trade_date=date(2026, 9, 25),
        india_vix=12.5,
        regime_classification="RISK_ON",
    )

    with patch.object(notifier, "send_message", return_value=True) as mock_send:
        assert notifier.send_card1(card1) is True
        assert notifier.send_card2(card2) is True
        assert notifier.send_regime(regime) is True
        assert mock_send.call_count == 3
