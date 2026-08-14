#!/bin/sh
set -eu

runtime_password="${OPEX_POSTGRES_RUNTIME_PASSWORD:-}"

if [ -n "${OPEX_POSTGRES_RUNTIME_PASSWORD_FILE:-}" ]; then
  if [ ! -r "${OPEX_POSTGRES_RUNTIME_PASSWORD_FILE}" ]; then
    echo "Runtime PostgreSQL password secret file cannot be read" >&2
    exit 1
  fi

  runtime_password="$(cat "${OPEX_POSTGRES_RUNTIME_PASSWORD_FILE}")"
fi

if [ -z "${runtime_password}" ]; then
  echo "Runtime PostgreSQL password is not configured" >&2
  exit 1
fi

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$runtime_password" <<'EOSQL'
SELECT format(
    'CREATE ROLE opex_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'runtime_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'opex_runtime'
) \gexec
EOSQL
