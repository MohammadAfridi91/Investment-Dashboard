from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.database import client as client_mod
from core.database.client import DatabaseClient


def _client() -> DatabaseClient:
    return DatabaseClient(supabase_url="https://fake.supabase.co", service_key="fake")


def _table_with_pages(total: int) -> MagicMock:
    """Fake PostgREST table that honours .range() like the real server (row cap included)."""
    data = [{"i": n} for n in range(total)]
    table = MagicMock()
    q = MagicMock()
    table.select.return_value = q
    for m in ("eq", "order", "in_"):
        getattr(q, m).return_value = q

    def _range(start: int, end: int) -> MagicMock:
        r = MagicMock()
        r.execute.return_value = MagicMock(data=data[start : end + 1])
        return r

    q.range.side_effect = _range
    return table


def test_select_pages_past_postgrest_cap() -> None:
    c = _client()
    c.supabase.table = MagicMock(return_value=_table_with_pages(2500))  # type: ignore[method-assign]
    rows = c.select("daily_prices")
    assert len(rows) == 2500
    assert [r["i"] for r in rows[:3]] == [0, 1, 2]


def test_select_limit_larger_than_page_is_honoured() -> None:
    c = _client()
    c.supabase.table = MagicMock(return_value=_table_with_pages(5000))  # type: ignore[method-assign]
    assert len(c.select("daily_prices", limit=1500)) == 1500
    assert len(c.select("daily_prices", limit=1)) == 1


def test_select_in_chunks_values() -> None:
    c = _client()
    table = _table_with_pages(3)
    c.supabase.table = MagicMock(return_value=table)  # type: ignore[method-assign]
    c.select_in("universe", "symbol", [f"S{i}" for i in range(450)])
    assert table.select.return_value.in_.call_count == 3  # 200 + 200 + 50


def test_bulk_upsert_logs_and_falls_back_on_pg_failure() -> None:
    c = DatabaseClient("https://fake.supabase.co", "fake", pg_dsn="postgresql://bad")
    mock_table = MagicMock()
    c.supabase.table = MagicMock(return_value=mock_table)  # type: ignore[method-assign]
    with (
        patch.object(c, "_pg_upsert", side_effect=RuntimeError("boom")),
        patch.object(client_mod.log, "warning") as warn,
    ):
        assert c.bulk_upsert("t", [{"a": 1}], ["a"]) == 1
    warn.assert_called_once()
    assert warn.call_args.kwargs["error"] == "RuntimeError: boom"
    mock_table.upsert.assert_called_once()


def test_pg_upsert_uses_union_of_columns_and_json_adapter() -> None:
    c = DatabaseClient("https://fake.supabase.co", "fake", pg_dsn="postgresql://x")
    captured: dict[str, Any] = {}

    def fake_execute_values(cur: Any, stmt: Any, values: Any) -> None:
        captured["values"] = values

    fake_conn = MagicMock()
    with (
        patch.object(client_mod, "execute_values", fake_execute_values),
        patch.object(client_mod.psycopg2, "connect", return_value=fake_conn),
    ):
        n = c._pg_upsert("t", [{"a": 1, "b": {"x": 1}}, {"a": 2, "c": 3}], ["a"])
    assert n == 2
    # columns are a, b, c -> missing keys become None instead of raising KeyError
    assert captured["values"][1][1] is None
    assert type(captured["values"][0][1]).__name__ == "Json"


def test_insert_is_insert_only() -> None:
    c = _client()
    table = MagicMock()
    c.supabase.table = MagicMock(return_value=table)  # type: ignore[method-assign]
    assert c.insert("sebi_compliance_log", [{"id": "1"}, {"id": "2"}]) == 2
    table.insert.assert_called_once()
    table.upsert.assert_not_called()


def test_insert_empty_is_noop() -> None:
    assert _client().insert("t", []) == 0


@pytest.mark.parametrize("n", [0, 1])
def test_bulk_upsert_empty_rows(n: int) -> None:
    assert _client().bulk_upsert("t", [], ["a"]) == 0
