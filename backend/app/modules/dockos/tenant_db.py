from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from psycopg.rows import dict_row
from .runtime_db import pool
from .observability import record_lock_wait


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
            started = time.perf_counter()
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'dockos:{tid}',))
            record_lock_wait((time.perf_counter() - started) * 1000.0)
            yield conn


def consume_gateway_replay(timestamp: str, nonce: str, signature: str, ttl_seconds: int) -> bool:
    token = hashlib.sha256(f'{timestamp}|{nonce}|{signature}'.encode('utf-8')).hexdigest()
    key = f'gateway-replay:{token}'
    with pool().connection() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            tid = _tenant_id(conn)
            set_tenant(conn, tid)
            conn.execute(
                "DELETE FROM dockos.settings WHERE key LIKE %s AND updated_at < now() - (%s * interval '1 second')",
                ('gateway-replay:%', max(60, int(ttl_seconds) * 2)),
            )
            row = conn.execute(
                "INSERT INTO dockos.settings(tenant_id,key,value) VALUES (%s,%s,%s::jsonb) ON CONFLICT (tenant_id,key) DO NOTHING RETURNING key",
                (tid, key, json.dumps({'timestamp': timestamp, 'nonce': nonce})),
            ).fetchone()
            return bool(row)


def load_kv(conn, prefixes=('state:','config:')):
    rows = conn.execute('SELECT key,value FROM dockos.settings').fetchall()
    return {row['key']: row['value'] for row in rows if any(row['key'].startswith(prefix) for prefix in prefixes)}


def save_kv(conn, values):
    tid = _tenant_id(conn)
    for key, value in values.items():
        conn.execute(
            'INSERT INTO dockos.settings(tenant_id,key,value) VALUES (%s,%s,%s::jsonb) ON CONFLICT (tenant_id,key) DO UPDATE SET value=excluded.value,updated_at=now()',
            (tid, key, json.dumps(value, ensure_ascii=False, default=str)),
        )


def db_status():
    try:
        with read_conn() as conn:
            versions=[row['version'] for row in conn.execute('SELECT version FROM dockos.schema_migrations ORDER BY version').fetchall()]
            return {'ok':'001_dockos_postgres' in versions,'migrations':versions,'tenant':tenant_key()}
    except Exception as error:
        return {'ok':False,'migrations':[],'tenant':tenant_key(),'error':str(error)[:300]}
