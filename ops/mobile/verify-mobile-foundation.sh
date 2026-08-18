#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
CORE="$ROOT/android-inventory/mobile-core/src/main/java/com/eay/mobile/core"
APP="$ROOT/android-inventory/app/src/main/java/com/eay/inventory"
INVENTORY_RES="$ROOT/android-inventory/app/src/main/res"
INVENTORY_MANIFEST="$ROOT/android-inventory/app/src/main/AndroidManifest.xml"
LOCALE_CONTRACT="$ROOT/config/eay_localization.json"
ADAPTER="$ROOT/android-inventory/field-presentation-adapter/src/main/java/com/eay/mobile/presentation/adapter/FieldPresentationAdapter.kt"
PRESENTATION="$ROOT/mobile-presentation-contracts/src/main/kotlin/com/eay/mobile/presentation/FieldPresentationModels.kt"
CONFIG="$ROOT/config/eay_mobile_platform.json"
PY_CORE="$ROOT/services/core-api/app/core"
CANONICAL="$APP/TerminalEventCanonical.kt"
EVENT_FACTORY="$APP/InventoryCountEventFactory.kt"
DATABASE="$APP/InventoryDatabase.kt"
QUEUE="$APP/InventoryOfflineQueue.kt"
COUNT_CONTROLLER="$APP/BlindCountTerminalController.kt"
COUNT_TASK="$APP/InventoryTerminalCountTask.kt"
TASK_CLIENT="$APP/InventoryTerminalTaskClient.kt"
MAIN_ACTIVITY="$APP/MainActivity.kt"
COUNT_CONTROLLER_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/BlindCountTerminalControllerTest.kt"
COUNT_TASK_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryTerminalCountTaskTest.kt"
TASK_CLIENT_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryTerminalTaskClientTest.kt"
ANDROID_EVENT_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/OfflineContractTest.kt"
BACKEND_EVENT_TEST="$ROOT/backend/tests/test_inventory_terminal_event_hash_contract.py"
BACKEND_TASK_TEST="$ROOT/backend/tests/test_inventory_terminal_task_contract.py"
GOLDEN_HASH="83fa7ef91803244218d6851f0ed217f66d9641d46e419fad79eb0b749c1dc291"

required="
$CORE/MobilePlatformContract.kt
$CORE/MobileOperationAdmission.kt
$CORE/MobileEventLedger.kt
$CORE/MobileTelemetryPolicy.kt
$CORE/MobileSyncEngine.kt
$CORE/FieldMission.kt
$CORE/ScannerIngress.kt
$CORE/BlindCountFlow.kt
$CORE/FleetHealth.kt
$CORE/RuntimeControl.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/MobileFoundationContractTest.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/MobileSyncEngineTest.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/FieldMissionTest.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/FleetHealthTest.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/RuntimeControlTest.kt
$ADAPTER
$PRESENTATION
$ROOT/android-inventory/field-presentation-adapter/src/test/java/com/eay/mobile/presentation/adapter/FieldPresentationAdapterTest.kt
$CANONICAL
$EVENT_FACTORY
$DATABASE
$QUEUE
$COUNT_CONTROLLER
$COUNT_TASK
$TASK_CLIENT
$MAIN_ACTIVITY
$INVENTORY_MANIFEST
$LOCALE_CONTRACT
$COUNT_CONTROLLER_TEST
$COUNT_TASK_TEST
$TASK_CLIENT_TEST
$ANDROID_EVENT_TEST
$BACKEND_EVENT_TEST
$BACKEND_TASK_TEST
$PY_CORE/mobile_policy.py
$PY_CORE/mobile_policy_signing.py
$PY_CORE/mobile_device_trust.py
$ROOT/backend/tests/test_inventory_production_identity_authority.py
$CONFIG
"

for file in $required; do
  test -f "$file" || { echo "missing mobile foundation file: $file" >&2; exit 1; }
done

grep -q '"production_ready": false' "$CONFIG"
grep -q '"production_activation_permitted": false' "$CONFIG"
grep -q '"main_merge_permitted": false' "$CONFIG"
grep -q 'DENY_MISSING_POLICY' "$CORE/MobileOperationAdmission.kt"
grep -q 'DENY_BINDING_MISMATCH' "$CORE/MobileOperationAdmission.kt"
grep -q 'DENY_INTEGRITY' "$CORE/MobileOperationAdmission.kt"
grep -q 'risk == OperationRisk.CRITICAL' "$CORE/MobileOperationAdmission.kt"
grep -q 'PAYLOAD_SUBSTITUTION' "$CORE/MobileEventLedger.kt"
grep -q 'SEQUENCE_COLLISION' "$CORE/MobileEventLedger.kt"
grep -q 'BUSINESS_CONFLICT' "$CORE/MobileSyncEngine.kt"
grep -q 'AUTH_BINDING_CHANGED' "$CORE/MobileSyncEngine.kt"
grep -q 'INSTALLATION_BINDING_CHANGED' "$CORE/MobileSyncEngine.kt"
grep -q 'fleet_device_token' "$CORE/FleetHealth.kt"
grep -q 'DISABLED_POLICY_MISMATCH' "$CORE/RuntimeControl.kt"
grep -q 'actor_id' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'canonical_payload' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'barcode' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'biometric' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'MissionGate.evaluate' "$ADAPTER"
grep -q 'MobileOperationAdmission' "$CORE/FieldMission.kt"
grep -q 'BlindCountLocationToken.hash(scan.value)' "$CORE/BlindCountFlow.kt"
grep -q 'UUID.fromString' "$CANONICAL"
grep -q 'OffsetDateTime.parse' "$CANONICAL"
grep -q 'acceptedScan.payloadHash == evidence.itemPayloadHash' "$EVENT_FACTORY"
grep -q 'MAX(deviceSequence)' "$DATABASE"
grep -q 'database.withTransaction' "$QUEUE"
grep -q 'maxDeviceSequence()' "$QUEUE"
grep -q 'enqueueConfirmedCount' "$QUEUE"
grep -q 'RetryableCountPersistenceException' "$QUEUE"
grep -q 'BlindCountFlow.verifyLocation' "$COUNT_CONTROLLER"
grep -q 'BlindCountFlow.scanItem' "$COUNT_CONTROLLER"
grep -q 'BlindCountFlow.confirmItem' "$COUNT_CONTROLLER"
grep -q 'eventSink.enqueueConfirmedCount' "$COUNT_CONTROLLER"
grep -q 'catch (_: RetryableCountPersistenceException)' "$COUNT_CONTROLLER"
grep -q 'InventoryTerminalCountTask' "$COUNT_TASK"
grep -q 'BlindCountLocationToken.hash(locationId)' "$COUNT_TASK"
grep -q 'PinnedApi.client' "$TASK_CLIENT"
grep -q 'AccessTokenMemory.freshOrNull' "$TASK_CLIENT"
grep -q 'ManagedDeviceIdentity' "$TASK_CLIENT"
grep -q 'X-EAY-Device-ID' "$TASK_CLIENT"
grep -q '/api/inventory/v1/terminal/tasks' "$TASK_CLIENT"
grep -q 'CONTRACT_REJECTED' "$TASK_CLIENT"
grep -q 'expected_quantity' "$TASK_CLIENT"
grep -q 'Duplicate terminal mission ID' "$TASK_CLIENT"
grep -q 'InventoryTerminalTaskClient(this)' "$MAIN_ACTIVITY"
grep -q 'BlindCountTerminalController(' "$MAIN_ACTIVITY"
grep -q 'InventorySyncWorker.enqueue(this)' "$MAIN_ACTIVITY"
grep -q 'R.string.terminal_' "$MAIN_ACTIVITY"
grep -q 'android:supportsRtl="true"' "$INVENTORY_MANIFEST"
grep -q 'reuses exact event identity' "$COUNT_CONTROLLER_TEST"
grep -q 'not mislabeled as retryable' "$COUNT_CONTROLLER_TEST"
grep -q 'no anonymous fallback' "$TASK_CLIENT_TEST"
grep -q "$GOLDEN_HASH" "$ANDROID_EVENT_TEST"
grep -q "$GOLDEN_HASH" "$BACKEND_EVENT_TEST"
grep -q '_terminal_mission_id' "$BACKEND_TASK_TEST"
grep -q 'tenant_bound' "$BACKEND_TASK_TEST"
grep -q 'MOBILE_POLICY_ALGORITHM = "ES256"' "$PY_CORE/mobile_policy_signing.py"
grep -q 'MAX_SIGNED_POLICY_LIFETIME_SECONDS = 300' "$PY_CORE/mobile_policy_signing.py"
grep -q 'MobileDeviceState.REPLACED' "$ROOT/services/core-api/tests/test_mobile_device_trust.py"
grep -q 'require_verified_identity' "$ROOT/backend/app/modules/inventory/router.py"

if grep -R -n -E 'Settings\.Secure\.ANDROID_ID|http://|WebView|addJavascriptInterface' "$CORE"; then
  echo "forbidden mobile-core authority/transport primitive detected" >&2
  exit 1
fi

if grep -R -n -E '(access|refresh|id)_token[[:space:]]*=[[:space:]]*"[^"$]+' "$CORE"; then
  echo "literal credential-like value detected in mobile core" >&2
  exit 1
fi

if grep -n -E 'OkHttpClient|CertificatePinner|newBuilder\(' "$TASK_CLIENT"; then
  echo "terminal task client must reuse PinnedApi instead of creating transport authority" >&2
  exit 1
fi

if grep -n -E '(status\.)?text[[:space:]]*=[[:space:]]*"' "$MAIN_ACTIVITY"; then
  echo "hard-coded user-facing terminal text detected" >&2
  exit 1
fi

if grep -n -E 'def (create_production_document|production_reconciliation|transition_document).*x_opex_(role|permissions)' "$ROOT/backend/app/modules/inventory/router.py"; then
  echo "production Inventory route exposes client-facing role/permission authority" >&2
  exit 1
fi

if grep -n -E 'tenant(Id)?|actor(Id)?|employee(Id)?|installation(Id)?|authBinding(Id)?|payloadHash|currentItemHash|expectedStock|systemStock|rawBarcode|latitude|longitude' "$PRESENTATION"; then
  echo "presentation contract leaked authority, hash, stock-truth or precise-location state" >&2
  exit 1
fi

if grep -n -E 'enabled[[:space:]]*=[[:space:]]*(true|false)' "$ADAPTER"; then
  echo "presentation adapter hard-codes mission enablement instead of using MissionGate" >&2
  exit 1
fi

if grep -n -E 'expectedStock|systemStock|expected_quantity|unit_cost|variance' "$COUNT_CONTROLLER" "$COUNT_TASK"; then
  echo "blind-count terminal contract leaked stock truth" >&2
  exit 1
fi

python3 - "$LOCALE_CONTRACT" "$INVENTORY_RES" <<'PY'
from pathlib import Path
import json
import re
import sys
import xml.etree.ElementTree as ET

contract = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = Path(sys.argv[2])
required_locales = contract.get("required_locales") or []
qualifiers = contract.get("android_resource_qualifiers") or {}
if len(required_locales) != 10 or set(qualifiers) != set(required_locales):
    raise SystemExit("Inventory terminal must consume the canonical 10-locale contract")

placeholder = re.compile(r"%\d+\$[a-zA-Z]")
resources = {}
for locale in required_locales:
    path = res / qualifiers[locale] / "strings.xml"
    if not path.is_file():
        raise SystemExit(f"missing Inventory terminal locale resource: {locale} -> {path}")
    root = ET.parse(path).getroot()
    values = {}
    for node in root.findall("string"):
        name = node.attrib.get("name")
        if name:
            values[name] = "".join(node.itertext())
    resources[locale] = values

baseline = resources[contract["default_locale"]]
for locale, values in resources.items():
    if set(values) != set(baseline):
        raise SystemExit(
            f"Inventory terminal locale key parity failure for {locale}: "
            f"missing={sorted(set(baseline) - set(values))} extra={sorted(set(values) - set(baseline))}"
        )
    for key, baseline_value in baseline.items():
        if set(placeholder.findall(values[key])) != set(placeholder.findall(baseline_value)):
            raise SystemExit(f"Inventory terminal placeholder parity failure for {locale}/{key}")

print(f"EAY Inventory terminal locale parity: PASS ({len(required_locales)} locales)")
PY

echo "EAY Mobile foundation static security contract: PASS"
