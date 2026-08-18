#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
CORE="$ROOT/android-inventory/mobile-core/src/main/java/com/eay/mobile/core"
CONFIG="$ROOT/config/eay_mobile_platform.json"

required="
$CORE/MobilePlatformContract.kt
$CORE/MobileOperationAdmission.kt
$CORE/MobileEventLedger.kt
$CORE/MobileTelemetryPolicy.kt
$ROOT/android-inventory/mobile-core/src/test/java/com/eay/mobile/core/MobileFoundationContractTest.kt
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
grep -q 'canonical_payload' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'barcode' "$CORE/MobileTelemetryPolicy.kt"
grep -q 'biometric' "$CORE/MobileTelemetryPolicy.kt"

if grep -R -n -E 'Settings\.Secure\.ANDROID_ID|http://|WebView|addJavascriptInterface' "$CORE"; then
  echo "forbidden mobile-core authority/transport primitive detected" >&2
  exit 1
fi

if grep -R -n -E '(access|refresh|id)_token[[:space:]]*=[[:space:]]*"[^"$]+' "$CORE"; then
  echo "literal credential-like value detected in mobile core" >&2
  exit 1
fi

echo "EAY Mobile foundation static security contract: PASS"
