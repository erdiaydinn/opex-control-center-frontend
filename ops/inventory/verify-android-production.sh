#!/usr/bin/env sh
set -eu

source_root="${1:-android-inventory/app/src/main}"
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
locale_contract="$repo_root/config/eay_localization.json"
main_activity="$source_root/java/com/eay/inventory/MainActivity.kt"
datawedge="$source_root/java/com/eay/inventory/DataWedge.kt"
feedback="$source_root/java/com/eay/inventory/TerminalFeedback.kt"
count_controller="$source_root/java/com/eay/inventory/BlindCountTerminalController.kt"
operational_controller="$source_root/java/com/eay/inventory/InventoryOperationalController.kt"
operational_client="$source_root/java/com/eay/inventory/InventoryOperationalTaskClient.kt"
operational_router="$repo_root/backend/app/modules/inventory/operational_mobile_router.py"
operational_claim="$repo_root/backend/app/modules/inventory/operational_claim.py"
operational_recovery="$repo_root/backend/app/modules/inventory/operational_recovery.py"
operational_v9="$repo_root/backend/migrations/009_inventory_operational_runtime_authority.sql"
app_gradle="$repo_root/android-inventory/app/build.gradle.kts"

for forbidden in 'ANDROID_ID' 'EncryptedSharedPreferences' 'HttpURLConnection' 'usesCleartextTraffic="true"' 'username.*password'; do
  if grep -R -n -E "$forbidden" "$source_root"; then
    echo "forbidden pilot behavior in production Android source: $forbidden" >&2
    exit 1
  fi
done

grep -R -q 'ManagedDeviceIdentity' "$source_root"
grep -R -q 'SupportOpenHelperFactory' "$source_root"
grep -R -q 'CertificatePinner' "$source_root"
grep -R -q 'AuthorizationRequest' "$source_root"
grep -R -q 'com.eay.inventory.SCAN' "$source_root"
test -f "$locale_contract" || { echo "missing canonical localization contract" >&2; exit 1; }
test -f "$datawedge" || { echo "missing production DataWedge contract" >&2; exit 1; }
test -f "$feedback" || { echo "missing terminal business feedback contract" >&2; exit 1; }
test -f "$count_controller" || { echo "missing blind-count controller" >&2; exit 1; }
test -f "$operational_controller" || { echo "missing operational controller" >&2; exit 1; }
test -f "$operational_client" || { echo "missing operational mobile client" >&2; exit 1; }
test -f "$operational_router" || { echo "missing operational mobile router" >&2; exit 1; }
test -f "$operational_claim" || { echo "missing signed operational claim authority" >&2; exit 1; }
test -f "$operational_recovery" || { echo "missing operational recovery authority" >&2; exit 1; }
test -f "$operational_v9" || { echo "missing operational runtime authority migration" >&2; exit 1; }

# Managed Zebra decode feedback must be explicit. This is decode acknowledgement,
# not business acceptance; EAY business ACK/NACK remains a separate terminal layer.
grep -q 'putString("PLUGIN_NAME", "BARCODE")' "$datawedge"
grep -q 'putString("configure_all_scanners", "true")' "$datawedge"
grep -q 'putString("decode_haptic_feedback", "1")' "$datawedge"
grep -q 'putString("decoding_led_feedback", "1")' "$datawedge"
grep -q 'putParcelableArray("PLUGIN_CONFIG", arrayOf(barcodePlugin, intentPlugin))' "$datawedge"
grep -q 'TerminalFeedbackRuntime.initialize' "$datawedge"

# Business result feedback must remain PII-free and distinct from scanner decode.
# CI only proves the implementation/budget contract; physical Zebra <100ms timing
# still requires field acceptance and is never inferred from this static gate.
grep -q 'LOCAL_DECISION_TARGET_MS = 100L' "$feedback"
grep -q 'ToneGenerator.TONE_PROP_ACK' "$feedback"
grep -q 'ToneGenerator.TONE_PROP_NACK' "$feedback"
grep -q 'VibrationEffect.createOneShot' "$feedback"
grep -q 'TerminalFeedbackRuntime.recordLocalDecision' "$count_controller"
grep -q 'TerminalFeedbackRuntime.accepted' "$count_controller"
grep -q 'TerminalFeedbackRuntime.rejected' "$count_controller"
grep -q 'TerminalFeedbackRuntime.recordLocalDecision' "$operational_controller"
grep -q 'TerminalFeedbackRuntime.accepted' "$operational_controller"
grep -q 'TerminalFeedbackRuntime.rejected' "$operational_controller"
if grep -n -E 'barcode|sku|employee|tenant|missionId|warehouseId' "$feedback" | grep -v -E '^.*(No barcode|No .*tenant|Business-result feedback|PII|mission or tenant).*'; then
  echo "terminal feedback must not carry operational identity or stock payload" >&2
  exit 1
fi

# Operational mission claim is a mutation: OIDC + device id alone is insufficient.
# Both client and backend bind claim to active shift + mission using the same fresh
# timestamp/nonce/hardware-backed device proof contract as terminal events.
grep -q 'InventoryOperationalClaimContract.hash' "$operational_client"
grep -q 'X-EAY-Request-Timestamp' "$operational_client"
grep -q 'X-EAY-Request-Nonce' "$operational_client"
grep -q 'X-EAY-Device-Signature' "$operational_client"
grep -q 'x_eay_request_timestamp' "$operational_router"
grep -q 'x_eay_request_nonce' "$operational_router"
grep -q 'x_eay_device_signature' "$operational_router"
grep -q 'claim_operational_mission_signed' "$operational_router"
grep -q '_verify_device_proof' "$operational_claim"
grep -q 'operational_claim_hash' "$operational_claim"

# Stale/shift-stranded operational claims require a governed supervisor release.
# Employee UI cannot steal/rebind a claim; control-plane release is permission +
# device-proof guarded and preserves historical evidence.
grep -q 'mobile_operational_claim_release' "$operational_router"
grep -q 'require_verified_identity(request, "completeInventory")' "$operational_router"
grep -q 'release_operational_claim' "$operational_router"
grep -q '_verify_device_proof' "$operational_recovery"
grep -q 'PRESERVE_NO_REBIND' "$operational_recovery"
grep -q 'OPERATIONAL_CLAIM_SUPERVISOR_RELEASED' "$operational_recovery"
grep -q "Claim sahibi kendi operational claim'ini supervisor release ile kapatamaz" "$operational_recovery"

# V9 closes runtime schema drift and ensures a replaced managed device cannot
# strand or inherit an operational claim. Replay responses and claims remain
# append-only evidence; only governed release metadata may change.
grep -q 'inventory_operational_intent_v9_check' "$operational_v9"
grep -q 'inventory_operational_claim_v9_guard' "$operational_v9"
grep -q 'inventory_operational_responses_immutable' "$operational_v9"
grep -q 'inventory_device_operational_recovery_v9' "$operational_v9"
grep -q "release_reason='DEVICE_REPLACED'" "$operational_v9"

# The production task and quantity-entry surfaces must use the shared typed Compose boundary.
# Compose callbacks remain presentation-only and return to signed authority paths.
grep -q 'EayTerminalRuntimeView' "$main_activity"
grep -q 'FieldPresentationAdapter.missionIntentCard' "$main_activity"
grep -q 'fieldUi.renderBlindCount' "$main_activity"
grep -q 'BlindCountPresentationCopy' "$main_activity"
grep -q 'missionClaimClient.claim' "$main_activity"
grep -q 'operationalClaimClient.claim' "$main_activity"
grep -q 'controller.enterQuantity' "$main_activity"
grep -q 'controller.confirmItem()' "$main_activity"
grep -q 'implementation(project(":field-presentation-adapter"))' "$app_gradle"
grep -q 'implementation(project(":field-ui-runtime"))' "$app_gradle"
if grep -q 'taskList.addView' "$main_activity"; then
  echo "legacy parallel task-button rendering must not bypass the shared Compose presentation boundary" >&2
  exit 1
fi
if grep -q -E 'quantityInput|confirmQuantity|EditText' "$main_activity"; then
  echo "legacy View-based quantity entry must not bypass the shared Compose blind-count surface" >&2
  exit 1
fi
if grep -q -E 'release_operational_claim|operational-missions/.*/release|OPERATIONAL_CLAIM_SUPERVISOR_RELEASED' "$main_activity"; then
  echo "employee terminal UI must not expose supervisor claim-release authority" >&2
  exit 1
fi

python3 - "$source_root/res" "$locale_contract" <<'PY'
from __future__ import annotations

from pathlib import Path
import json
import re
import sys
import xml.etree.ElementTree as ET

res = Path(sys.argv[1])
contract = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
required = contract.get("required_locales") or []
qualifiers = contract.get("android_resource_qualifiers") or {}

if contract.get("authority") != "platform_core":
    raise SystemExit("Inventory localization authority drifted from Platform Core")
if contract.get("english_only_production_exception_allowed") is not False:
    raise SystemExit("English-only production exception must remain disabled")
if len(required) != 10 or set(qualifiers) != set(required):
    raise SystemExit("Inventory must inherit the exact 10-locale Platform Core contract")
if "ar" not in set(contract.get("rtl_locales") or []):
    raise SystemExit("Arabic RTL must remain mandatory")

placeholder_pattern = re.compile(r"%(?:\d+\$)?[a-zA-Z]")


def resources(path: Path) -> dict[str, tuple[str, tuple[str, ...]]]:
    if not path.is_file():
        raise SystemExit(f"missing mandatory Inventory locale resource: {path}")
    root = ET.parse(path).getroot()
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    for node in root.findall("string"):
        name = node.attrib.get("name")
        if not name or node.attrib.get("translatable") == "false":
            continue
        text = "".join(node.itertext())
        placeholders = tuple(placeholder_pattern.findall(text))
        result[name] = (text, placeholders)
    return result

paths = {
    locale: res / qualifiers[locale] / "strings.xml"
    for locale in required
}
baseline = resources(paths[contract["default_locale"]])
baseline_keys = set(baseline)

for locale, path in paths.items():
    current = resources(path)
    current_keys = set(current)
    if current_keys != baseline_keys:
        raise SystemExit(
            f"Inventory locale key parity failure for {locale}: "
            f"missing={sorted(baseline_keys-current_keys)} "
            f"extra={sorted(current_keys-baseline_keys)}"
        )
    for key in sorted(baseline_keys):
        expected_placeholders = baseline[key][1]
        actual_placeholders = current[key][1]
        if actual_placeholders != expected_placeholders:
            raise SystemExit(
                f"Inventory placeholder parity failure for {locale}/{key}: "
                f"expected={expected_placeholders} actual={actual_placeholders}"
            )

required_completion_keys = {
    "terminal_finish_location",
    "terminal_finish_location_title",
    "terminal_finish_location_message",
    "terminal_cancel",
    "terminal_finish_location_confirm",
    "terminal_location_complete_queued",
    "terminal_completion_retry",
}
missing_completion = sorted(required_completion_keys - baseline_keys)
if missing_completion:
    raise SystemExit(
        f"durable location completion localization contract incomplete: {missing_completion}"
    )

print("Inventory localization parity: PASS (10 locales + placeholder parity + RTL contract)")
PY

echo "Android production source gate passed"
