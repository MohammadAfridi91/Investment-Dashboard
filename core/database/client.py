from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import Json, execute_values
from supabase import Client, create_client

from core.utils.logging import get_logger

# Load .env (repo root or CWD) without overriding real environment variables.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
load_dotenv(override=False)

log = get_logger("db")

# PostgREST caps a single response (Supabase default: 1000 rows).
PAGE_SIZE = 1000
# Keep `in.(...)` filters comfortably below URL length limits.
IN_CHUNK_SIZE = 200


def _json_serializable(val: Any) -> Any:
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: _json_serializable(v) for k, v in row.items()} for row in rows]


def _pg_value(val: Any) -> Any:
    """Adapt Python values psycopg2 cannot bind natively (dict/list -> JSON)."""
    if isinstance(val, (dict, list)):
        return Json(val)
    return val


class DatabaseClient:
    """Unified DB client: fast PostgreSQL bulk upserts with a logged PostgREST fallback."""

    def __init__(
        self,
        supabase_url: str | None = None,
        service_key: str | None = None,
        pg_dsn: str | None = None,
    ) -> None:
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        key = service_key or os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be provided")

        self.supabase: Client = create_client(url, key)
        self._client: Client = self.supabase  # Backward-compatible alias
        self.pg_dsn = pg_dsn or os.environ.get("SUPABASE_DB_URL")

    @classmethod
    def from_env(cls) -> DatabaseClient:
        """Factory method to instantiate client using environment variables."""
        return cls()

    @contextmanager
    def pg(self) -> Iterator[psycopg2.extensions.connection]:
        if not self.pg_dsn:
            raise RuntimeError("SUPABASE_DB_URL is not configured for direct PostgreSQL access")
        conn = psycopg2.connect(self.pg_dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def bulk_upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        conflict_cols: list[str],
    ) -> int:
        if not rows:
            return 0

        if self.pg_dsn:
            try:
                return self._pg_upsert(table, rows, conflict_cols)
            except Exception as exc:
                # Never swallow silently: the fallback is ~10x slower and may hide a real bug.
                log.warning(
                    "pg_bulk_upsert_failed_falling_back_to_rest",
                    table=table,
                    rows=len(rows),
                    error=f"{type(exc).__name__}: {exc}",
                )

        conflict_str = ",".join(conflict_cols) if conflict_cols else ""
        return self.upsert(table, rows, on_conflict=conflict_str)

    def _pg_upsert(self, table: str, rows: list[dict[str, Any]], conflict_cols: list[str]) -> int:
        # Union of keys (first-seen order) so heterogeneous rows do not raise KeyError.
        cols = list(dict.fromkeys(k for r in rows for k in r))
        update_cols = [c for c in cols if c not in conflict_cols]
        if update_cols:
            action: sql.Composable = sql.SQL("DO UPDATE SET {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
                )
            )
        else:
            action = sql.SQL("DO NOTHING")
        stmt = sql.SQL("INSERT INTO {t} ({cols}) VALUES %s ON CONFLICT ({conf}) {action}").format(
            t=sql.Identifier(table),
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            conf=sql.SQL(", ").join(sql.Identifier(c) for c in conflict_cols),
            action=action,
        )
        values = [tuple(_pg_value(r.get(c)) for c in cols) for r in rows]
        with self.pg() as conn, conn.cursor() as cur:
            execute_values(cur, stmt, values)
        return len(rows)

    def upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        on_conflict: str | None = None,
        chunk_size: int = 500,
    ) -> int:
        if not rows:
            return 0
        cleaned = _clean_rows(rows)
        for i in range(0, len(cleaned), chunk_size):
            chunk = cleaned[i : i + chunk_size]
            if on_conflict:
                self.supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()
            else:
                self.supabase.table(table).upsert(chunk).execute()
        return len(rows)

    def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        chunk_size: int = 200,
    ) -> int:
        """Insert-only write. Raises on conflict instead of overwriting (append-only tables)."""
        if not rows:
            return 0
        cleaned = _clean_rows(rows)
        for i in range(0, len(cleaned), chunk_size):
            self.supabase.table(table).insert(cleaned[i : i + chunk_size]).execute()
        return len(rows)

    def _fetch_paged(
        self, make_query: Callable[[], Any], limit: int | None
    ) -> list[dict[str, Any]]:
        """Fetch all pages (or up to `limit` rows) so PostgREST's row cap never truncates."""
        out: list[dict[str, Any]] = []
        start = 0
        while limit is None or len(out) < limit:
            want = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(out))
            res = make_query().range(start, start + want - 1).execute()
            page = cast(list[dict[str, Any]], res.data or [])
            out.extend(page)
            if len(page) < want:
                break
            start += want
        return out

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        def make_query() -> Any:
            q = self.supabase.table(table).select(columns)
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            if order:
                parts = order.replace(" ", ".").split(".")
                col = parts[0]
                is_desc = len(parts) > 1 and parts[1].lower() == "desc"
                q = q.order(col, desc=is_desc)
            return q

        return self._fetch_paged(make_query, limit or None)

    def select_in(
        self,
        table: str,
        column: str,
        values: list[Any],
        columns: str = "*",
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        out: list[dict[str, Any]] = []
        for i in range(0, len(values), IN_CHUNK_SIZE):
            chunk = values[i : i + IN_CHUNK_SIZE]

            def make_query(chunk: list[Any] = chunk) -> Any:
                return self.supabase.table(table).select(columns).in_(column, chunk)

            out.extend(self._fetch_paged(make_query, None))
        return out


# Aliases for backward compatibility
DB = DatabaseClient


def get_client() -> DatabaseClient:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    pg_dsn = os.environ.get("SUPABASE_DB_URL")
    return DatabaseClient(url, key, pg_dsn)


@contextmanager
def db_connection(db_url: str | None = None) -> Iterator[psycopg2.extensions.connection]:
    url = db_url or os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL is required for migrations")
    conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_migrations(
    migrations_dir: str | Path = "migrations",
    db_url: str | None = None,
) -> list[str]:
    mig_dir = Path(migrations_dir)
    files = sorted(mig_dir.glob("*.sql"))
    applied: list[str] = []
    with db_connection(db_url) as conn, conn.cursor() as cur:
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
            applied.append(f.name)
    return applied
