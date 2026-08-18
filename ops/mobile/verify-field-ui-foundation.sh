#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
UI="$ROOT/android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui"
RES="$ROOT/android-field-ui/field-ui/src/main/res"
LOCALE_CONTRACT="$ROOT/config/eay_localization.json"
MOBILE_CONFIG="$ROOT/config/eay_mobile_platform.json"

required="
$ROOT/android-field-ui/settings.gradle.kts
$ROOT/android-field-ui/build.gradle.kts
$ROOT/android-field-ui/field-ui/build.gradle.kts
$UI/FieldUiModels.kt
$UI/EayFieldTheme.kt
$UI/EayTerminalShell.kt
$LOCALE_CONTRACT
$MOBILE_CONFIG
"

for file in $required; do
  test -f "$file" || { echo "missing field UI file: $file" >&2; exit 1; }
done

grep -q 'com.android.library.*9.2.0' "$ROOT/android-field-ui/build.gradle.kts"
grep -q 'org.jetbrains.kotlin.plugin.compose.*2.3.21' "$ROOT/android-field-ui/build.gradle.kts"
grep -q 'compileSdk = 37' "$ROOT/android-field-ui/field-ui/build.gradle.kts"
grep -q 'compose-bom:2026.06.00' "$ROOT/android-field-ui/field-ui/build.gradle.kts"
grep -q 'minHeight = 56.dp' "$UI/EayTerminalShell.kt"
grep -q 'minHeight = 64.dp' "$UI/EayTerminalShell.kt"
grep -q 'stringResource(R.string.eay_terminal_brand)' "$UI/EayTerminalShell.kt"
grep -q 'pluralStringResource(' "$UI/EayTerminalShell.kt"
grep -q 'stringResource(R.string.field_sync_description' "$UI/EayTerminalShell.kt"

if grep -R -n -E 'WebView|addJavascriptInterface|expectedStock|systemStock|rawBarcode|println\(|Log\.(v|d|i|w|e)\(' "$UI"; then
  echo "forbidden field UI primitive or data leak detected" >&2
  exit 1
fi

if grep -R -n -E 'authorization|access_token|refresh_token|device_id|actor_id|employee_id|latitude|longitude' "$UI"; then
  echo "field UI must not own auth or raw identity/coordinate authority" >&2
  exit 1
fi

if grep -R -n -E 'Sıradaki görevler|Gözlenen adet|satır tamamlandı|Adedi doğrula|Senkron durumu|Çevrimdışı|İnceleme gerekli' "$UI"; then
  echo "hard-coded localized field UI text detected" >&2
  exit 1
fi

if grep -R -n 'androidx.compose.material.icons' "$UI" || grep -q 'material-icons' "$ROOT/android-field-ui/field-ui/build.gradle.kts"; then
  echo "broad icon dependency is not allowed in the field UI foundation" >&2
  exit 1
fi

if grep -R -n -E 'LayoutDirection\.Ltr|TextDirection\.Ltr|supportsRtl="false"' "$ROOT/android-field-ui"; then
  echo "forced LTR behavior is forbidden; RTL must remain locale-driven" >&2
  exit 1
fi

python3 - "$RES" "$LOCALE_CONTRACT" "$MOBILE_CONFIG" <<'PY'
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

res = Path(sys.argv[1])
contract_path = Path(sys.argv[2])
mobile_config_path = Path(sys.argv[3])
contract = json.loads(contract_path.read_text(encoding="utf-8"))
mobile_config = json.loads(mobile_config_path.read_text(encoding="utf-8"))

if contract.get("capability") != "LOC":
    raise SystemExit("localization contract must be owned by LOC capability")
if contract.get("authority") != "platform_core":
    raise SystemExit("localization authority must remain Platform Core")
if contract.get("default_locale") != "en" or contract.get("fallback_locale") != "en":
    raise SystemExit("localization fallback/default must remain explicit English")
if contract.get("english_only_production_exception_allowed") is not False:
    raise SystemExit("English-only production exception must remain disabled")

mobile_localization = mobile_config.get("localization") or {}
if mobile_localization.get("contract") != "config/eay_localization.json":
    raise SystemExit("mobile localization contract path drifted from canonical config/eay_localization.json")
if mobile_localization.get("authority") != "platform_core":
    raise SystemExit("mobile localization authority must remain Platform Core")
if mobile_localization.get("mandatory_locale_parity") is not True:
    raise SystemExit("mobile mandatory locale parity must remain enabled")
if mobile_localization.get("english_first_production_exception") is not False:
    raise SystemExit("mobile English-first production exception must remain disabled")
if mobile_localization.get("rtl_locale_driven") is not True:
    raise SystemExit("mobile RTL must remain locale-driven")

required_locales = contract.get("required_locales") or []
if len(required_locales) != 10 or len(required_locales) != len(set(required_locales)):
    raise SystemExit("localization contract must define exactly 10 unique required locales")
rtl_locales = set(contract.get("rtl_locales") or [])
if "ar" not in rtl_locales:
    raise SystemExit("Arabic RTL is mandatory")
if not rtl_locales.issubset(set(required_locales)):
    raise SystemExit("RTL locales must also be required locales")

qualifiers = contract.get("android_resource_qualifiers") or {}
if set(qualifiers) != set(required_locales):
    raise SystemExit("Android qualifier map must exactly cover required locales")

plural_contract = contract.get("plural_categories") or {}
if set(plural_contract) != set(required_locales):
    raise SystemExit("plural category map must exactly cover required locales")
for locale, categories in plural_contract.items():
    if not categories or len(categories) != len(set(categories)) or "other" not in categories:
        raise SystemExit(f"invalid plural category contract for {locale}")

locales = {}
for locale in required_locales:
    qualifier = qualifiers[locale]
    path = res / qualifier / "strings.xml"
    if not path.is_file():
        raise SystemExit(f"missing Android resources for required locale {locale}: {path}")
    locales[locale] = path


def keys(path: Path):
    root = ET.parse(path).getroot()
    out = set()
    for child in root:
        name = child.attrib.get("name")
        if not name:
            continue
        if child.tag == "string" and child.attrib.get("translatable") == "false":
            continue
        if child.tag in {"string", "plurals"}:
            out.add((child.tag, name))
    return out

baseline = keys(locales[contract["default_locale"]])
for locale, path in locales.items():
    current = keys(path)
    if current != baseline:
        missing = sorted(baseline - current)
        extra = sorted(current - baseline)
        raise SystemExit(
            f"locale parity failure for {locale}: missing={missing} extra={extra}"
        )

required_plurals = {"field_sync_pending", "blind_count_completed_lines"}
for locale, path in locales.items():
    root = ET.parse(path).getroot()
    plural_nodes = {node.attrib.get("name"): node for node in root.findall("plurals")}
    missing_names = sorted(required_plurals - set(plural_nodes))
    if missing_names:
        raise SystemExit(f"plural contract failure for {locale}: missing={missing_names}")

    required_categories = set(plural_contract[locale])
    for plural_name in required_plurals:
        actual_categories = {
            item.attrib.get("quantity") for item in plural_nodes[plural_name].findall("item")
        }
        missing_categories = sorted(required_categories - actual_categories)
        if missing_categories:
            raise SystemExit(
                f"CLDR plural category failure for {locale}/{plural_name}: "
                f"missing={missing_categories}"
            )

print(
    "EAY Field UI locale parity: PASS "
    f"({len(required_locales)} required locales; RTL={sorted(rtl_locales)}; CLDR categories enforced; mobile binding canonical)"
)
PY

echo "EAY Field UI static contract: PASS"
