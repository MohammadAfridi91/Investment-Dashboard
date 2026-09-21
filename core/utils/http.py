from __future__ import annotations

import time
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.utils.logging import get_logger

log = get_logger("http")

NSE_HOMEPAGE = "https://www.nseindia.com/"
NSE_ARCHIVE_BASE = "https://archives.nseindia.com"

class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} {url}: {body[:200]}")
        self.status = status
        self.url = url

class NSEHttpClient:
    def __init__(self, user_agent: str, delay_ms: int = 500, timeout: int = 30):
        self.user_agent = user_agent
        self.delay = delay_ms / 1000.0
        self.timeout = timeout
        self._session = self._bootstrap_session()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _bootstrap_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(self._headers())
        try:
            s.get(NSE_HOMEPAGE, timeout=self.timeout)
            time.sleep(self.delay)
        except Exception as e:
            log.warning("nse_bootstrap_failed", error=str(e))
        return s

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=8),
           retry=retry_if_exception_type((requests.RequestException, HttpError)),
           reraise=True)
    def get(self, url: str, allow_cookie_retry: bool = True) -> bytes:
        time.sleep(self.delay)
        r = self._session.get(url, timeout=self.timeout)
        if r.status_code in (401, 403) and allow_cookie_retry:
            log.warning("nse_session_stale_rebootstrap", url=url)
            self._session = self._bootstrap_session()
            time.sleep(self.delay)
            r = self._session.get(url, timeout=self.timeout)
        if r.status_code >= 400:
            raise HttpError(r.status_code, url, r.text)
        return r.content

class PlainHttpClient:
    def __init__(self, user_agent: str, delay_ms: int = 500, timeout: int = 30,
                 extra_headers: dict[str, str] | None = None):
        self.delay = delay_ms / 1000.0
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        if extra_headers:
            self._session.headers.update(extra_headers)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=8),
           retry=retry_if_exception_type((requests.RequestException, HttpError)),
           reraise=True)
    def get(self, url: str, **kwargs: Any) -> bytes:
        time.sleep(self.delay)
        r = self._session.get(url, timeout=self.timeout, **kwargs)
        if r.status_code >= 400:
            raise HttpError(r.status_code, url, r.text)
        return r.content
