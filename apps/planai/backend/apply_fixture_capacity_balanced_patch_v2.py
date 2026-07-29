
from pathlib import Path
import shutil
from datetime import datetime

ENGINE = Path("engine.py")
MAPPER = Path("fixture_capacity_mapper.py")

MARK = "# === PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V2 ==="

PATCH_BLOCK = r