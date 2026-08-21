#!/usr/bin/env sh
set -eu

required="EAY_ANDROID_KEYSTORE_B64 EAY_ANDROID_KEY_ALIAS EAY_ANDROID_KEY_PASSWORD EAY_ANDROID_STORE_PASSWORD EAY_API_BASE_URL EAY_OIDC_ISSUER EAY_OIDC_CLIENT_ID EAY_TLS_PIN_PRIMARY EAY_TLS_PIN_BACKUP"
for name in $required; do
  eval "value=\${$name:-}"
  [ -n "$value" ] || { echo "missing required managed-release input: $name" >&2; exit 1; }
done

case "$EAY_API_BASE_URL" in https://*) ;; *) echo "EAY_API_BASE_URL must use HTTPS" >&2; exit 1;; esac
case "$EAY_OIDC_ISSUER" in https://*) ;; *) echo "EAY_OIDC_ISSUER must use HTTPS" >&2; exit 1;; esac
[ "$EAY_TLS_PIN_PRIMARY" != "$EAY_TLS_PIN_BACKUP" ] || { echo "primary and backup TLS pins must differ" >&2; exit 1; }
echo "managed-release inputs structurally valid"
