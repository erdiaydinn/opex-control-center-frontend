#!/usr/bin/env sh
set -eu

source_root="${1:-android-inventory/app/src/main}"
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
echo "Android production source gate passed"
