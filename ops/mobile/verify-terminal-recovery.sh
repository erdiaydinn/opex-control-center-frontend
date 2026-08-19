#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
APP="$ROOT/android-inventory/app/src/main/java/com/eay/inventory"
PRESENTATION="$ROOT/mobile-presentation-contracts/src/main/kotlin/com/eay/mobile/presentation/FieldPresentationModels.kt"
FIELD_UI="$ROOT/android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui/EayTerminalShell.kt"
RUNTIME="$ROOT/android-inventory/field-ui-runtime/src/main/java/com/eay/mobile/fieldui/runtime/EayTerminalRuntimeView.kt"
ADAPTER="$ROOT/android-inventory/field-presentation-adapter/src/main/java/com/eay/mobile/presentation/adapter/FieldPresentationAdapter.kt"
RES="$ROOT/android-inventory/app/src/main/res"
RECOVERY="$APP/InventoryRecoveryContract.kt"
RECOVERY_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryRecoveryContractTest.kt"

for file in "$PRESENTATION" "$FIELD_UI" "$RUNTIME" "$ADAPTER" "$RECOVERY" "$RECOVERY_TEST"; do
  test -f "$file" || { echo "missing terminal recovery contract: $file" >&2; exit 1; }
done

grep -q 'FieldRecoveryBannerModel' "$PRESENTATION"
grep -q 'FieldRecoveryActionKind' "$PRESENTATION"
grep -q 'RecoveryBanner' "$FIELD_UI"
grep -q 'recovery = current.model.recovery' "$RUNTIME"
grep -q 'fun recoveryBanner' "$ADAPTER"
grep -q 'AUTH_BINDING_CHANGED' "$RECOVERY"
grep -q 'REQUEST_SECURITY_REVIEW' "$RECOVERY"
grep -q 'authBindingMismatchCannotBeFixedBySigningInAgain' "$RECOVERY_TEST"
grep -q 'quarantinedEvidenceNeverBecomesClientRetry' "$RECOVERY_TEST"

if grep -R -n -E 'dao\.(retry|delete|quarantine)|events\(\)\.(retry|delete)|reassign_terminal|supersede_attempt|payloadHash|authBindingId|tenantId|employeeId|deviceId|leaseId|attemptId' \
  "$ROOT/android-field-ui/field-ui/src/main" \
  "$ROOT/android-inventory/field-ui-runtime/src/main" \
  "$ROOT/android-inventory/field-presentation-adapter/src/main"; then
  echo "recovery presentation crossed into mutation or authority state" >&2
  exit 1
fi

python3 - "$PRESENTATION" "$RES" <<'PY'
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

presentation = Path(sys.argv[1]).read_text(encoding="utf-8")
res = Path(sys.argv[2])

enum = re.search(r"enum class FieldRecoveryActionKind\s*\{([^}]*)\}", presentation, re.S)
if not enum:
    raise SystemExit("FieldRecoveryActionKind is missing")
actions = {value.strip().strip(",") for value in enum.group(1).splitlines() if value.strip()}
allowed = {"NONE", "SIGN_IN_AGAIN", "RELOAD_MISSIONS"}
if actions != allowed:
    raise SystemExit(f"recovery presentation action surface changed: {sorted(actions)}")

required_keys = {
    "terminal_recovery_title_info",
    "terminal_recovery_title_blocking",
    "terminal_recovery_title_security",
    "terminal_recovery_wait_auto",
    "terminal_recovery_device",
    "terminal_recovery_supervisor",
    "terminal_recovery_security",
    "terminal_recovery_integrity",
    "terminal_recovery_reload",
    "terminal_recovery_sign_in",
}
locale_dirs = [
    "values",
    "values-tr",
    "values-de",
    "values-ar",
    "values-es",
    "values-fr",
    "values-it",
    "values-nl",
    "values-pl",
    "values-pt-rBR",
]
for directory in locale_dirs:
    path = res / directory / "recovery_strings.xml"
    if not path.is_file():
        raise SystemExit(f"missing recovery locale resource: {path}")
    root = ET.parse(path).getroot()
    keys = {item.attrib.get("name") for item in root.findall("string")}
    if keys != required_keys:
        missing = sorted(required_keys - keys)
        extra = sorted(keys - required_keys)
        raise SystemExit(f"recovery locale drift in {directory}: missing={missing} extra={extra}")

print("terminal recovery contract: OK")
PY
