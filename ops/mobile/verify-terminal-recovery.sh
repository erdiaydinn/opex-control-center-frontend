#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
APP="$ROOT/android-inventory/app/src/main/java/com/eay/inventory"
PRESENTATION="$ROOT/mobile-presentation-contracts/src/main/kotlin/com/eay/mobile/presentation/FieldPresentationModels.kt"
FIELD_UI="$ROOT/android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui/EayTerminalShell.kt"
RUNTIME="$ROOT/android-inventory/field-ui-runtime/src/main/java/com/eay/mobile/fieldui/runtime/EayTerminalRuntimeView.kt"
ADAPTER="$ROOT/android-inventory/field-presentation-adapter/src/main/java/com/eay/mobile/presentation/adapter/FieldPresentationAdapter.kt"
SESSION_ADAPTER="$ROOT/android-inventory/field-presentation-adapter/src/main/java/com/eay/mobile/presentation/adapter/SessionRecoveryPresentationAdapter.kt"
RES="$ROOT/android-inventory/app/src/main/res"
RECOVERY="$APP/InventoryRecoveryContract.kt"
RECOVERY_PRESENTATION="$APP/InventoryRecoveryPresentation.kt"
RECOVERY_CASE_CLIENT="$APP/InventoryRecoveryCaseClient.kt"
SYNC_WORKER="$APP/InventorySyncWorker.kt"
DATABASE="$APP/InventoryDatabase.kt"
TASK_RECOVERY_PRESENTATION="$APP/InventoryTaskFetchRecoveryPresentation.kt"
MISSION_RECOVERY_PRESENTATION="$APP/InventoryMissionExecutionRecoveryPresentation.kt"
MAIN="$APP/MainActivity.kt"
RECOVERY_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryRecoveryContractTest.kt"
RECOVERY_PRESENTATION_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryRecoveryPresentationTest.kt"
RECOVERY_CASE_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryRecoveryCaseContractTest.kt"
MISSION_RECOVERY_TEST="$ROOT/android-inventory/app/src/test/java/com/eay/inventory/InventoryMissionExecutionRecoveryPresentationTest.kt"
SESSION_ADAPTER_TEST="$ROOT/android-inventory/field-presentation-adapter/src/test/java/com/eay/mobile/presentation/adapter/SessionRecoveryPresentationAdapterTest.kt"

for file in \
  "$PRESENTATION" \
  "$FIELD_UI" \
  "$RUNTIME" \
  "$ADAPTER" \
  "$SESSION_ADAPTER" \
  "$RECOVERY" \
  "$RECOVERY_PRESENTATION" \
  "$RECOVERY_CASE_CLIENT" \
  "$SYNC_WORKER" \
  "$DATABASE" \
  "$TASK_RECOVERY_PRESENTATION" \
  "$MISSION_RECOVERY_PRESENTATION" \
  "$MAIN" \
  "$RECOVERY_TEST" \
  "$RECOVERY_PRESENTATION_TEST" \
  "$RECOVERY_CASE_TEST" \
  "$MISSION_RECOVERY_TEST" \
  "$SESSION_ADAPTER_TEST"; do
  test -f "$file" || { echo "missing terminal recovery contract: $file" >&2; exit 1; }
done

grep -q 'FieldRecoveryBannerModel' "$PRESENTATION"
grep -q 'FieldSessionRecoveryBannerModel' "$PRESENTATION"
grep -q 'FieldRecoveryActionKind' "$PRESENTATION"
grep -q 'RecoveryBanner' "$FIELD_UI"
grep -q 'SessionRecoveryBanner' "$FIELD_UI"
grep -q 'recovery = current.model.recovery' "$RUNTIME"
grep -q 'sessionRecovery = current.model.sessionRecovery' "$RUNTIME"
grep -q 'fun recoveryBanner' "$ADAPTER"
grep -q 'SessionRecoveryPresentationAdapter' "$SESSION_ADAPTER"
grep -q 'AUTH_BINDING_CHANGED' "$RECOVERY"
grep -q 'REQUEST_SECURITY_REVIEW' "$RECOVERY"
grep -q 'SERVER_CONTRACT_MISMATCH' "$RECOVERY"
grep -q 'WAIT_FOR_SUPERVISOR_REVIEW' "$RECOVERY"
grep -q 'authBindingMismatchCannotBeFixedBySigningInAgain' "$RECOVERY_TEST"
grep -q 'policyRejectionRoutesToSecurityNotSupervisor' "$RECOVERY_TEST"
grep -q 'serverContractAndPermanentRejectionRouteToIntegrityNotSupervisor' "$RECOVERY_TEST"
grep -q 'operationalConflictRoutesToSupervisorThenBecomesWaitOnlyAfterCaseBinding' "$RECOVERY_TEST"
grep -q 'quarantinedEvidenceNeverBecomesClientRetry' "$RECOVERY_TEST"
grep -q 'blocksNewMissionStarts' "$RECOVERY_PRESENTATION"
grep -q 'supervisorRoutingDoesNotExposeMutationActionOrGloballyStopUnrelatedMissions' "$RECOVERY_PRESENTATION_TEST"
grep -q 'unsupportedDurableUiIntentsBecomeIntegrityBlockWithoutAction' "$RECOVERY_PRESENTATION_TEST"

grep -q 'InventoryRecoveryCaseContract.from' "$RECOVERY_CASE_CLIENT"
grep -q 'TerminalEventCanonical.hash(event.canonicalPayload)' "$RECOVERY_CASE_CLIENT"
grep -q 'X-EAY-Request-Timestamp' "$RECOVERY_CASE_CLIENT"
grep -q 'X-EAY-Request-Nonce' "$RECOVERY_CASE_CLIENT"
grep -q 'X-EAY-Device-Signature' "$RECOVERY_CASE_CLIENT"
grep -q 'PRESERVE_NO_CLIENT_PROMOTION' "$RECOVERY_CASE_CLIENT"
grep -q 'routeSupervisorRecovery' "$SYNC_WORKER"
grep -q 'InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW' "$SYNC_WORKER"
grep -q 'recoveryCandidates' "$SYNC_WORKER"
grep -q 'markRecoveryRequested' "$SYNC_WORKER"
grep -q 'recoveryCaseId' "$DATABASE"
grep -q 'MIGRATION_4_5' "$DATABASE"
grep -q 'canonical payload hash substitution is rejected before supervisor request' "$RECOVERY_CASE_TEST"
grep -q 'security device policy and integrity quarantine cannot enter supervisor business recovery' "$RECOVERY_CASE_TEST"

grep -q 'InventoryTaskFetchCode.AUTH_REQUIRED' "$TASK_RECOVERY_PRESENTATION"
grep -q 'FieldRecoveryActionKind.SIGN_IN_AGAIN' "$TASK_RECOVERY_PRESENTATION"
grep -q 'FieldRecoveryActionKind.RELOAD_MISSIONS' "$TASK_RECOVERY_PRESENTATION"
grep -q 'InventoryMissionClaimCode.BUSINESS_CONFLICT' "$MISSION_RECOVERY_PRESENTATION"
grep -q 'fun leaseExpiredPolicy' "$MISSION_RECOVERY_PRESENTATION"
grep -q 'FieldRecoveryActionKind.RELOAD_MISSIONS' "$MISSION_RECOVERY_PRESENTATION"
grep -q 'expired lease requires fresh mission reload not client lease extension' "$MISSION_RECOVERY_TEST"
grep -q 'device and authority rejection expose no client recovery mutation' "$MISSION_RECOVERY_TEST"
grep -q 'session recovery exposes sign in without durable evidence fields' "$SESSION_ADAPTER_TEST"
grep -q 'session recovery exposes read only mission reload' "$SESSION_ADAPTER_TEST"

grep -q 'InventoryRecoveryContract.summarize(unsettled)' "$MAIN"
grep -q 'localRecoverySummary' "$MAIN"
grep -q 'sessionRecoveryBanner' "$MAIN"
grep -q 'InventoryTaskFetchRecoveryPresentation.banner' "$MAIN"
grep -q 'InventoryMissionExecutionRecoveryPresentation.claimBanner' "$MAIN"
grep -q 'InventoryMissionExecutionRecoveryPresentation.leaseExpiredBanner' "$MAIN"
grep -q 'sessionRecovery = sessionRecoveryBanner' "$MAIN"
grep -q 'onRecoveryAction = { action -> handleRecoveryAction(action) }' "$MAIN"
grep -q 'FieldRecoveryActionKind.SIGN_IN_AGAIN' "$MAIN"
grep -q 'FieldRecoveryActionKind.RELOAD_MISSIONS' "$MAIN"
grep -q 'taskSelectionEnabled = false' "$MAIN"
grep -q 'recovery = recoveryBanner' "$MAIN"
grep -q '!globallyBlocked' "$MAIN"
grep -q 'sessionRecoveryBanner == null' "$MAIN"

if grep -R -n -E 'dao\.(retry|delete|quarantine)|events\(\)\.(retry|delete)|reassign_terminal|supersede_attempt|payloadHash|authBindingId|tenantId|employeeId|deviceId|leaseId|attemptId' \
  "$ROOT/android-field-ui/field-ui/src/main" \
  "$ROOT/android-inventory/field-ui-runtime/src/main" \
  "$ROOT/android-inventory/field-presentation-adapter/src/main"; then
  echo "recovery presentation crossed into mutation or authority state" >&2
  exit 1
fi

if grep -R -n -E 'extendLease|renewLease|reviveLease|rebindLease|reassignMission' \
  "$MISSION_RECOVERY_PRESENTATION" \
  "$MAIN"; then
  echo "mission recovery attempted to create client lease authority" >&2
  exit 1
fi

# Supervisor recovery is routed by the signed worker/client boundary, never by
# presentation models or MainActivity UI actions.
if grep -R -n 'REQUEST_SUPERVISOR_REVIEW' \
  "$ROOT/mobile-presentation-contracts/src/main" \
  "$ROOT/android-field-ui/field-ui/src/main" \
  "$ROOT/android-inventory/field-ui-runtime/src/main" \
  "$ROOT/android-inventory/field-presentation-adapter/src/main" \
  "$MAIN"; then
  echo "supervisor recovery leaked into presentation/UI authority" >&2
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
    "terminal_recovery_wait_supervisor",
    "terminal_recovery_request_supervisor",
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
