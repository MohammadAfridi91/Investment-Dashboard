"""
Supabase + direct-Postgres dual client.

Three env vars are required -- there is no derived fallback:

  SUPABASE_URL          e.g. https://xxxxx.supabase.co
  SUPABASE_SERVICE_KEY  service_role JWT -- used ONLY for the Supabase
                         REST/PostgREST client. It is a bearer token,
                         not a Postgres password, and must never be
                         treated as one.
  SUPABASE_DB_URL       Postgres connection string used by bulk_upsert().
                         MUST be the Supavisor pooler string (Transaction
                         mode, port 6543) -- NOT the direct
                         db.<ref>.supabase.co:5432 string. Supabase's
                         direct connection is IPv6-only by default and
                         GitHub-hosted runners are IPv4-only, so the
                         direct string will not route from Actions.
                         Get it from: Supabase Dashboard -> Connect ->
                         "Transaction pooler", then substitute the real
                         database password for [YOUR-PASSWORD].
"""
import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values
from supabase import Client, create_client


class DatabaseClient:
    def __init__(self, supabase_url: str, service_key: str, pg_dsn: str):
        self.supabase: Client = create_client(supabase_url, service_key)
        self.pg_dsn = pg_dsn

    @contextmanager
    def pg(self):
        conn = psycopg2.connect(self.pg_dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def bulk_upsert(self, table: str, rows: list[dict], conflict_cols: list[str]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        conflict = ', '.join(conflict_cols)
        update_cols = [c for c in cols if c not in conflict_cols]
        set_clause = ', '.join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
        )
        with self.pg() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql,
                               [tuple(r[c] for c in cols) for r in rows])
        return len(rows)


def get_client() -> DatabaseClient:
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    pg_dsn = os.environ['SUPABASE_DB_URL']
    return DatabaseClient(url, key, pg_dsn)
