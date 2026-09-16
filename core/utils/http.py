import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return s


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8))
def fetch(session: requests.Session, url: str, delay_ms: int = 500) -> bytes:
    time.sleep(delay_ms / 1000)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def prewarm_nse_session() -> requests.Session:
    """Pre-warm NSE session for www.nseindia.com/api/* endpoints only.
       NOT needed for archives.nseindia.com (static CDN)."""
    s = get_session()
    s.get('https://www.nseindia.com/', timeout=15)
    return s
