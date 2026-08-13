from __future__ import annotations

import os
from contextlib import contextmanager
from psycopg.rows import dict_row
from .runtime_db import pool


def tenant_key():
    return os.getenv('DOCKOS_TENANT_KEY','ys_tr').strip().lower()


def _tenant_id(conn):
    key = tenant_key()
    row = conn.execute('SELECT id FROM dockos.tenants WHERE tenant_key=%s',(key,)).fetchone()
    if not row:
        row = conn.execute('INSERT INTO dockos.tenants(tenant_key,display_name) VALUES (%s,%s) RETURNING id',(key,key.upper())).fetchone()
    return str(row[0] if not isinstance(row,dict) else row['id'])


def set_tenant(conn, tid):
    conn.execute("SELECT set_config('dockos.tenant_id', %s, true)",(tid,))


@contextmanager
def read_conn():
    with pool().connection() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            tid = _tenant_id(conn)
            set_tenant(conn, tid)
            yield conn


@contextmanager
def write_conn():
    with pool().connection() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            tid = _tenant_id(conn)
            set_tenant(conn, tid)
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'dockos:{tid}',))
            yield conn
