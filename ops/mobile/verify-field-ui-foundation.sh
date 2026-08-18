#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
UI="$ROOT/android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui"
RES="$ROOT/android-field-ui/field-ui/src/main/res"

required="
$ROOT/android-field-ui/settings.gradle.kts
$ROOT/android-field-ui/build.gradle.kts
$ROOT/android-field-ui/field-ui/build.gradle.kts
$UI/FieldUiModels.kt
$UI/EayFieldTheme.kt
$UI/EayTerminalShell.kt
$RES/values/strings.xml
$RES/values-tr/strings.xml
$RES/values-de/strings.xml
$RES/values-ar/strings.xml
$RES/values-fr/strings.xml
$RES/values-es/strings.xml
$RES/values-it/strings.xml
$RES/values-nl/strings.xml
$RES/values-pl/strings.xml
$RES/values-pt-rBR/strings.xml
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
  echo "forced LTR behavior is forbidden; Arabic RTL must remain locale-driven" >&2
  exit 1
fi

python3 - "$RES" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

res = Path(sys.argv[1])
locales = {
    "en": res / "values" / "strings.xml",
    "tr-TR": res / "values-tr" / "strings.xml",
    "de": res / "values-de" / "strings.xml",
    "ar": res / "values-ar" / "strings.xml",
    "fr": res / "values-fr" / "strings.xml",
    "es": res / "values-es" / "strings.xml",
    "it": res / "values-it" / "strings.xml",
    "nl": res / "values-nl" / "strings.xml",
    "pl": res / "values-pl" / "strings.xml",
    "pt-BR": res / "values-pt-rBR" / "strings.xml",
}


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

baseline = keys(locales["en"])
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
    plural_names = {node.attrib.get("name") for node in root.findall("plurals")}
    missing = sorted(required_plurals - plural_names)
    if missing:
        raise SystemExit(f"plural contract failure for {locale}: missing={missing}")

print("EAY Field UI locale parity: PASS (10 mandatory locales)")
PY

echo "EAY Field UI static contract: PASS"
