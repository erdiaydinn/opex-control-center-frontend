#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
UI="$ROOT/android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui"

required="
$ROOT/android-field-ui/settings.gradle.kts
$ROOT/android-field-ui/build.gradle.kts
$ROOT/android-field-ui/field-ui/build.gradle.kts
$UI/FieldUiModels.kt
$UI/EayFieldTheme.kt
$UI/EayTerminalShell.kt
"

for file in $required; do
  test -f "$file" || { echo "missing field UI file: $file" >&2; exit 1; }
done

grep -q 'com.android.library.*9.2.0' "$ROOT/android-field-ui/build.gradle.kts"
grep -q 'org.jetbrains.kotlin.plugin.compose.*2.3.10' "$ROOT/android-field-ui/build.gradle.kts"
grep -q 'compileSdk = 37' "$ROOT/android-field-ui/field-ui/build.gradle.kts"
grep -q 'compose-bom:2026.06.00' "$ROOT/android-field-ui/field-ui/build.gradle.kts"
grep -q 'minHeight = 56.dp' "$UI/EayTerminalShell.kt"
grep -q 'minHeight = 64.dp' "$UI/EayTerminalShell.kt"

if grep -R -n -E 'WebView|addJavascriptInterface|expectedStock|systemStock|rawBarcode|println\(|Log\.(v|d|i|w|e)\(' "$UI"; then
  echo "forbidden field UI primitive or data leak detected" >&2
  exit 1
fi

if grep -R -n -E 'authorization|access_token|refresh_token|device_id|actor_id|employee_id|latitude|longitude' "$UI"; then
  echo "field UI must not own auth or raw identity/coordinate authority" >&2
  exit 1
fi

echo "EAY Field UI static contract: PASS"
