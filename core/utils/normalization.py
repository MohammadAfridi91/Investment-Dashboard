from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_client_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).upper().strip()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s)
    return s


def strip_column_names(cols: list[str]) -> list[str]:
    return [c.strip() for c in cols]
