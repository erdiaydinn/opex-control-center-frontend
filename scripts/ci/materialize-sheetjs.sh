#!/usr/bin/env bash
set -euo pipefail

VERSION="0.20.3"
URL="https://cdn.sheetjs.com/xlsx-${VERSION}/xlsx-${VERSION}.tgz"
TARGET="vendor/xlsx-${VERSION}.tgz"
EXPECTED_SHA512_B64="oLDq3jw7AcLqKWH2AhCpVTZl8mf6X2YReP+Neh0SJUzV/BdZYjth94tG5toiMB1PPrYtxOCfaoUCkvtuH+3AJA=="

mkdir -p vendor

verify() {
  python - "$TARGET" "$EXPECTED_SHA512_B64" <<'PY'
import base64
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
if not path.is_file():
    raise SystemExit(1)
actual = base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode("ascii")
if actual != expected:
    raise SystemExit(f"SheetJS integrity mismatch: expected {expected}, got {actual}")
PY
}

if verify 2>/dev/null; then
  echo "SheetJS ${VERSION} already materialized with expected integrity."
  exit 0
fi

rm -f "$TARGET"
curl --fail --location --silent --show-error --retry 3 --retry-all-errors \
  "$URL" --output "$TARGET"
verify

echo "SheetJS ${VERSION} materialized from the pinned official CDN artifact."
