import json
import os
import shutil
from datetime import date
from pathlib import Path
from threading import RLock


STATE_LOCK = RLock()
STATE_PATH = Path(
    os.getenv("DOCKOS_STATE_FILE", str(Path(__file__).with_name("dockos_state.json")))
)


def load_state(collections, settings):
    """Restore pilot state without replacing the list objects imported by service.py."""
    with STATE_LOCK:
        if not STATE_PATH.exists():
            save_state(collections, settings)
            return
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        for key, target in collections.items():
            value = payload.get(key)
            if isinstance(value, list):
                target[:] = value
        restored_settings = payload.get("settings")
        if isinstance(restored_settings, dict):
            settings.update(restored_settings)


def save_state(collections, settings):
    """Atomic single-process pilot persistence. Production may swap this for a DB adapter."""
    with STATE_LOCK:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: value for key, value in collections.items()}
        payload["settings"] = settings
        temporary = STATE_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(STATE_PATH)
        backup_root = os.getenv("DOCKOS_BACKUP_DIR", "").strip()
        if backup_root:
            backup_dir = Path(backup_root)
            backup_dir.mkdir(parents=True, exist_ok=True)
            daily_backup = backup_dir / f"dockos_state_{date.today().isoformat()}.json"
            backup_temp = daily_backup.with_suffix(".tmp")
            shutil.copy2(STATE_PATH, backup_temp)
            backup_temp.replace(daily_backup)
            retention = max(7, int(os.getenv("DOCKOS_BACKUP_RETENTION_DAYS", "30") or 30))
            backups = sorted(backup_dir.glob("dockos_state_*.json"), reverse=True)
            for old_backup in backups[retention:]:
                old_backup.unlink(missing_ok=True)
