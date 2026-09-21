from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import psycopg2
from psycopg2.extras import execute_values
from supabase import Client, create_client


def _load_env_if_present() -> None:
    for p in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in os.environ:
                        os.environ[k] = v


_load_env_if_present()


def _json_serializable(val: Any) -> Any:
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: _json_serializable(v) for k, v in row.items()} for row in rows]


class DatabaseClient:
    """Unified DB client supporting high-speed PostgreSQL bulk upserts

    with automatic fallback to Supabase REST (PostgREST) when running
    in IPv6-restricted or secret-constrained environments (e.g. GitHub Actions).
    """

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

        # Try psycopg2 execute_values if pg_dsn is configured
        if self.pg_dsn:
            try:
                cols = list(rows[0].keys())
                conflict = ", ".join(conflict_cols)
                update_cols = [c for c in cols if c not in conflict_cols]
                set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
                sql = (
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
                    f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
                )
                with self.pg() as conn, conn.cursor() as cur:
                    execute_values(
                        cur,
                        sql,
                        [tuple(r[c] for c in cols) for r in rows],
                    )
                return len(rows)
            except Exception:
                # Log or fallback to PostgREST
                pass

        # Resilient fallback to Supabase PostgREST in batches
        conflict_str = ",".join(conflict_cols) if conflict_cols else ""
        return self.upsert(table, rows, on_conflict=conflict_str)

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

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        q = self.supabase.table(table).select(columns)
        for k, v in (filters or {}).items():
            q = q.eq(k, v)
        if order:
            q = q.order(order)
        if limit:
            q = q.limit(limit)
        res = q.execute()
        return cast(list[dict[str, Any]], res.data or [])

    def select_in(
        self,
        table: str,
        column: str,
        values: list[Any],
        columns: str = "*",
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        res = self.supabase.table(table).select(columns).in_(column, values).execute()
        return cast(list[dict[str, Any]], res.data or [])


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
