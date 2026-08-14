from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock

_LOCK = Lock()
_RESERVATION_LATENCY_MS = deque(maxlen=5000)
_LOCK_WAIT_MS = deque(maxlen=5000)
_FAILED_BOOKINGS = 0
_LAST_BQ_SYNC_EPOCH = 0.0
_LAST_BQ_SYNC_OK = False


def _percentile(values, pct):
    data = sorted(values)
    if not data:
        return 0.0
    idx = min(len(data) - 1, max(0, math.ceil((pct / 100) * len(data)) - 1))
    return float(data[idx])


def record_reservation(latency_ms: float, ok: bool) -> None:
    global _FAILED_BOOKINGS
    with _LOCK:
        _RESERVATION_LATENCY_MS.append(float(latency_ms))
        if not ok:
            _FAILED_BOOKINGS += 1


def record_lock_wait(wait_ms: float) -> None:
    with _LOCK:
        _LOCK_WAIT_MS.append(float(wait_ms))


def record_bigquery_sync(ok: bool) -> None:
    global _LAST_BQ_SYNC_EPOCH, _LAST_BQ_SYNC_OK
    with _LOCK:
        _LAST_BQ_SYNC_OK = bool(ok)
        if ok:
            _LAST_BQ_SYNC_EPOCH = time.time()


def snapshot(service, pool_stats=None):
    now = time.time()
    with _LOCK:
        reservation = list(_RESERVATION_LATENCY_MS)
        locks = list(_LOCK_WAIT_MS)
        failed = _FAILED_BOOKINGS
        bq_epoch = _LAST_BQ_SYNC_EPOCH
        bq_ok = _LAST_BQ_SYNC_OK

    outbox = list(getattr(service, 'MOCK_NOTIFICATION_OUTBOX', []))
    pending = [row for row in outbox if row.get('status') in {'PENDING', 'FAILED', 'WAITING_CONFIG'}]
    retry = sum(1 for row in outbox if int(row.get('attempts') or 0) > 0 and row.get('status') != 'SENT')
    dead = sum(1 for row in outbox if row.get('status') == 'DEAD')
    oldest = 0.0
    for row in pending:
        value = row.get('created_at') or row.get('due_at')
        if not value:
            continue
        try:
            from datetime import datetime
            age = max(0.0, now - datetime.fromisoformat(value).timestamp())
            oldest = max(oldest, age)
        except Exception:
            pass

    stats = dict(pool_stats or {})
    pool_size = float(stats.get('pool_size') or 0)
    pool_available = float(stats.get('pool_available') or 0)
    pool_max = float(stats.get('pool_max') or 0)
    saturation = 0.0
    denominator = pool_max or pool_size
    if denominator > 0:
        saturation = max(0.0, min(1.0, (pool_size - pool_available) / denominator))

    return {
        'reservation_latency_p50_ms': _percentile(reservation, 50),
        'reservation_latency_p95_ms': _percentile(reservation, 95),
        'reservation_latency_p99_ms': _percentile(reservation, 99),
        'reservation_samples': len(reservation),
        'lock_wait_p95_ms': _percentile(locks, 95),
        'lock_wait_p99_ms': _percentile(locks, 99),
        'failed_bookings_total': failed,
        'outbox_oldest_age_seconds': oldest,
        'notification_retry_total': retry,
        'notification_dead_total': dead,
        'bigquery_sync_lag_seconds': max(0.0, now - bq_epoch) if bq_epoch else -1.0,
        'bigquery_last_sync_ok': bq_ok,
        'db_pool_saturation_ratio': saturation,
        'db_pool_requests_waiting': int(stats.get('requests_waiting') or 0),
        'db_pool_size': int(pool_size),
        'db_pool_available': int(pool_available),
    }


def render_prometheus(values: dict) -> str:
    lines = []
    for key, value in values.items():
        metric = 'dockos_' + key
        if isinstance(value, bool):
            value = 1 if value else 0
        lines.append(f'{metric} {value}')
    return '\n'.join(lines) + '\n'
