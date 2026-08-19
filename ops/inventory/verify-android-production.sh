#!/usr/bin/env sh
set -eu

source_root="${1:-android-inventory/app/src/main}"
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
locale_contract="$repo_root/config/eay_localization.json"
main_activity="$source_root/java/com/eay/inventory/MainActivity.kt"
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

# The production task surface must use the shared typed Compose boundary. The Compose callback is
# presentation-only and must still return to the existing signed server mission claim path.
grep -q 'EayTerminalRuntimeView' "$main_activity"
grep -q 'FieldPresentationAdapter.missionIntentCard' "$main_activity"
grep -q 'missionClaimClient.claim' "$main_activity"
grep -q 'implementation(project(":field-presentation-adapter"))' "$app_gradle"
grep -q 'implementation(project(":field-ui-runtime"))' "$app_gradle"
if grep -q 'taskList.addView' "$main_activity"; then
  echo "legacy parallel task-button rendering must not bypass the shared Compose presentation boundary" >&2
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
