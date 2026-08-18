#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
CORE="$ROOT/android-inventory/mobile-core/src/main/java/com/eay/mobile/core"
ADAPTER="$ROOT/android-inventory/field-presentation-adapter/src/main/java/com/eay/mobile/presentation/adapter/FieldPresentationAdapter.kt"
PRESENTATION="$ROOT/mobile-presentation-contracts/src/main/kotlin/com/eay/mobile/presentation/FieldPresentationModels.kt"
CONFIG="$ROOT/config/eay_mobile_platform.json"
PY_CORE="$ROOT/services/core-api/app/core"

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

echo "EAY Mobile foundation static security contract: PASS"
