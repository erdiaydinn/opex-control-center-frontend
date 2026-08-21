import copy
import json
import os
import shutil
from datetime import date
from pathlib import Path
from threading import RLock, local

from .runtime_db import enabled as postgres_enabled
from .tenant_db import load_kv, read_conn, save_kv, write_conn


STATE_PATH = Path(os.getenv('DOCKOS_STATE_FILE', str(Path(__file__).with_name('dockos_state.json'))))


def _row_key(name, row):
    if name == 'purchase_orders': return str(row.get('po_number') or row.get('po_order_id') or '')
    if name == 'reservations': return str(row.get('reservation_no') or '')
    if name == 'slot_capacity': return (row.get('warehouse_name'), row.get('date'), row.get('slot'))
    if name == 'supplier_capacity': return (row.get('warehouse_name'), row.get('date'), row.get('slot'), row.get('supplier_name'))
    if name == 'supplier_daily_limits': return (row.get('warehouse_name'), row.get('supplier_name'), row.get('date'))
    if name == 'supplier_access': return str(row.get('email') or '').casefold()
    if name == 'notification_outbox': return str(row.get('key') or '')
    if name == 'audit_log':
        return (row.get('timestamp'), row.get('action'), row.get('entity_type'), str(row.get('entity_id')), row.get('user_email'))
    return json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)


def _merge_list(name, baseline, local_rows, remote_rows):
    base = {_row_key(name, row): row for row in (baseline or [])}
    local_map = {_row_key(name, row): row for row in (local_rows or [])}
    remote = {_row_key(name, row): row for row in (remote_rows or [])}

    if name != 'audit_log':
        for key in set(base) - set(local_map):
            remote.pop(key, None)
    for key, row in local_map.items():
        if key not in base or row != base[key]:
            remote[key] = copy.deepcopy(row)

    if name == 'audit_log':
        # Audit is logically append-only: never propagate local trimming/deletion.
        for key, row in local_map.items():
            if key not in base:
                remote[key] = copy.deepcopy(row)
        rows = list(remote.values())
        rows.sort(key=lambda item: str(item.get('timestamp') or ''))
        return rows[-5000:]
    return list(remote.values())


def _apply_rows_preserving_identity(name, target, incoming):
    """Refresh rows without invalidating references already held by service functions.

    Several canonical RC7.5 mutation paths resolve a reservation/PO before taking
    STATE_LOCK. PostgreSQL mode refreshes state when the lock is entered. Replacing
    every dict object would leave those local references stale and make a successful
    edit/cancel disappear after commit. Preserve the existing dict object for the
    same natural key and refresh its contents in place.
    """
    existing = {_row_key(name, row): row for row in target if isinstance(row, dict)}
    refreshed = []
    for source in incoming:
        key = _row_key(name, source)
        current = existing.get(key)
        if isinstance(current, dict) and isinstance(source, dict):
            current.clear()
            current.update(copy.deepcopy(source))
            refreshed.append(current)
        else:
            refreshed.append(copy.deepcopy(source))
    target[:] = refreshed


class CrossProcessStateLock:
    def __init__(self):
        self._lock = RLock()
        self._local = local()
        self.collections = None
        self.settings = None
        self.baseline = {}

    def bind(self, collections, settings):
        self.collections = collections
        self.settings = settings

    def _apply(self, values):
        if self.collections is None:
            return
        for name, target in self.collections.items():
            key = f'state:{name}'
            if key in values and isinstance(values[key], list):
                _apply_rows_preserving_identity(name, target, values[key])
        if self.settings is not None:
            for key, value in values.items():
                if key.startswith('config:'):
                    self.settings[key[7:]] = copy.deepcopy(value)
        self.baseline = copy.deepcopy(values)

    def __enter__(self):
        self._lock.acquire()
        depth = getattr(self._local, 'depth', 0)
        self._local.depth = depth + 1
        if postgres_enabled() and depth == 0:
            cm = write_conn()
            conn = cm.__enter__()
            self._local.cm = cm
            self._local.conn = conn
            self._apply(load_kv(conn))
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            depth = getattr(self._local, 'depth', 1) - 1
            self._local.depth = depth
            if postgres_enabled() and depth == 0:
                cm = getattr(self._local, 'cm', None)
                try:
                    if cm is not None:
                        cm.__exit__(exc_type, exc, tb)
                finally:
                    self._local.conn = None
                    self._local.cm = None
        finally:
            self._lock.release()
        return False

    def current_conn(self):
        return getattr(self._local, 'conn', None)


STATE_LOCK = CrossProcessStateLock()


def persistence_mode():
    return 'postgres' if postgres_enabled() else 'json'


def _state_values(collections, settings):
    values = {f'state:{name}': copy.deepcopy(value) for name, value in collections.items()}
    values.update({f'config:{name}': copy.deepcopy(value) for name, value in settings.items()})
    return values


def refresh_state():
    if not postgres_enabled() or STATE_LOCK.collections is None:
        return
    if STATE_LOCK.current_conn() is not None:
        return
    with STATE_LOCK._lock:
        with read_conn() as conn:
            STATE_LOCK._apply(load_kv(conn))


def load_state(collections, settings):
    STATE_LOCK.bind(collections, settings)
    if postgres_enabled():
        from .mock_data import MOCK_WAREHOUSES
        configured = [item.strip() for item in os.getenv('DOCKOS_DC_NAMES', '').split(',') if item.strip()]
        if configured:
            MOCK_WAREHOUSES[:] = [{'warehouse_name': name} for name in configured]
        with STATE_LOCK:
            conn = STATE_LOCK.current_conn()
            values = load_kv(conn)
            has_state = any(key.startswith('state:') for key in values)
            if not has_state:
                for target in collections.values():
                    target.clear()
                initial = _state_values(collections, settings)
                save_kv(conn, initial)
                STATE_LOCK.baseline = copy.deepcopy(initial)
        return

    with STATE_LOCK._lock:
        if not STATE_PATH.exists():
            save_state(collections, settings)
            return
        try:
            payload = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return
        for key, target in collections.items():
            value = payload.get(key)
            if isinstance(value, list):
                target[:] = value
        restored_settings = payload.get('settings')
        if isinstance(restored_settings, dict):
            settings.update(restored_settings)


def _merge_and_save_outside_lock(collections, settings):
    local_values = _state_values(collections, settings)
    baseline = copy.deepcopy(STATE_LOCK.baseline)
    with write_conn() as conn:
        remote = load_kv(conn)
        merged = copy.deepcopy(remote)
        for name in collections:
            key = f'state:{name}'
            merged[key] = _merge_list(name, baseline.get(key, []), local_values.get(key, []), remote.get(key, []))
        for name in settings:
            key = f'config:{name}'
            local_value = local_values.get(key)
            if key not in baseline or local_value != baseline.get(key):
                merged[key] = copy.deepcopy(local_value)
        save_kv(conn, merged)
        STATE_LOCK._apply(merged)


def save_state(collections, settings):
    if postgres_enabled():
        conn = STATE_LOCK.current_conn()
        values = _state_values(collections, settings)
        if conn is not None:
            save_kv(conn, values)
            STATE_LOCK.baseline = copy.deepcopy(values)
            return
        with STATE_LOCK._lock:
            _merge_and_save_outside_lock(collections, settings)
        return

    with STATE_LOCK._lock:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: value for key, value in collections.items()}
        payload['settings'] = settings
        temporary = STATE_PATH.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        temporary.replace(STATE_PATH)
        backup_root = os.getenv('DOCKOS_BACKUP_DIR', '').strip()
        if backup_root:
            backup_dir = Path(backup_root)
            backup_dir.mkdir(parents=True, exist_ok=True)
            daily_backup = backup_dir / f'dockos_state_{date.today().isoformat()}.json'
            backup_temp = daily_backup.with_suffix('.tmp')
            shutil.copy2(STATE_PATH, backup_temp)
            backup_temp.replace(daily_backup)
            retention = max(7, int(os.getenv('DOCKOS_BACKUP_RETENTION_DAYS', '30') or 30))
            backups = sorted(backup_dir.glob('dockos_state_*.json'), reverse=True)
            for old_backup in backups[retention:]:
                old_backup.unlink(missing_ok=True)
