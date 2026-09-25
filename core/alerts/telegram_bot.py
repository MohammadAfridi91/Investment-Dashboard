"""Telegram bot notifier for dispatching pre-flight trade cards and macro alerts."""

from __future__ import annotations

import os
from typing import Any

import requests
import structlog

from core.alerts.formatters import (
    format_card1_markdown,
    format_card2_markdown,
    format_regime_markdown,
)
from core.models import MarketRegimeRow, TradeCheckCardRow

log = structlog.get_logger()


class TelegramNotifier:
    """Dispatches trade check cards and regime alerts via Telegram Bot API."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Returns True if bot token and chat ID are both present."""
        return bool(self.bot_token and self.chat_id)

    def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Sends a text message to the specified or default chat ID.

        Returns True on successful delivery (HTTP 200), False otherwise.
        Never raises an uncaught exception to protect pipeline continuity.
        """
        target_chat = chat_id or self.chat_id
        if not self.bot_token or not target_chat:
            log.warning(
                "telegram_not_configured",
                has_token=bool(self.bot_token),
                has_chat_id=bool(target_chat),
            )
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                log.info("telegram_alert_sent", chat_id=target_chat)
                return True
            log.error(
                "telegram_send_failed",
                status_code=resp.status_code,
                response=resp.text,
            )
            return False
        except Exception as e:
            log.error("telegram_transport_error", error=str(e))
            return False

    def send_card1(
        self,
        card: TradeCheckCardRow,
        chat_id: str | None = None,
    ) -> bool:
        """Formats and sends a Card 1 Tactical Swing pre-flight alert."""
        text = format_card1_markdown(card)
        return self.send_message(text, chat_id=chat_id)

    def send_card2(
        self,
        card: TradeCheckCardRow,
        chat_id: str | None = None,
    ) -> bool:
        """Formats and sends a Card 2 Strategic Core pre-flight alert."""
        text = format_card2_markdown(card)
        return self.send_message(text, chat_id=chat_id)

    def send_regime(
        self,
        regime: MarketRegimeRow,
        chat_id: str | None = None,
    ) -> bool:
        """Formats and sends a macro market regime update."""
        text = format_regime_markdown(regime)
        return self.send_message(text, chat_id=chat_id)
