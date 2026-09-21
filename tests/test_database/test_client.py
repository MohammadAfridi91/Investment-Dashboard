from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from core.database.client import DB, DatabaseClient, get_client


def test_database_client_initialization() -> None:
    client = DatabaseClient(
        supabase_url="https://fake-project.supabase.co",
        service_key="fake-service-key",
    )
    assert client.supabase is not None
    assert client._client is not None


def test_database_client_resilient_bulk_upsert_postgrest_fallback() -> None:
    client = DatabaseClient(
        supabase_url="https://fake-project.supabase.co",
        service_key="fake-service-key",
    )
    # Mock PostgREST table upsert
    mock_table = MagicMock()
    mock_upsert = MagicMock()
    mock_table.upsert.return_value = mock_upsert
    mock_upsert.execute.return_value = MagicMock(data=[{"id": 1}])
    client.supabase.table = MagicMock(return_value=mock_table)  # type: ignore[method-assign]

    rows = [{"symbol": "TCS", "price": 4000.0}]
    count = client.bulk_upsert("daily_prices", rows, conflict_cols=["symbol"])
    assert count == 1
    mock_table.upsert.assert_called_once()


def test_get_client_factory() -> None:
    with patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"}):
        c = get_client()
        assert isinstance(c, DB)
