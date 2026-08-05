#!/bin/sh
set -eu

: "${OPEX_POSTGRES_RUNTIME_PASSWORD:?Set OPEX_POSTGRES_RUNTIME_PASSWORD}"

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$OPEX_POSTGRES_RUNTIME_PASSWORD" <<'EOSQL'
SELECT format(
    'CREATE ROLE opex_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'runtime_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'opex_runtime'
) \gexec
EOSQL
