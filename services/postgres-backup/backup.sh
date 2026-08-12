#!/bin/sh

set -u

BACKUP_DIR="${BACKUP_DIR:-/backups}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${OPEX_POSTGRES_DB:-opex}"
POSTGRES_USER="${POSTGRES_USER:-opex_migrator}"
INTERVAL_HOURS="${OPEX_BACKUP_INTERVAL_HOURS:-24}"
RETENTION_DAYS="${OPEX_BACKUP_RETENTION_DAYS:-14}"
STATUS_FILE="${BACKUP_DIR}/backup-status.json"

if [ -n "${PGPASSWORD_FILE:-}" ]; then
  if [ ! -r "${PGPASSWORD_FILE}" ]; then
    echo "[backup] PostgreSQL password secret file cannot be read" >&2
    exit 1
  fi

  PGPASSWORD="$(cat "${PGPASSWORD_FILE}")"
  export PGPASSWORD
fi

if [ -z "${PGPASSWORD:-}" ]; then
  echo "[backup] PostgreSQL password is not configured" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

write_status() {
  status="$1"
  started_at="$2"
  completed_at="$3"
  filename="$4"
  size_bytes="$5"
  message="$6"

  temporary_file="${STATUS_FILE}.tmp"

  cat > "${temporary_file}" <<EOF
{
  "status": "${status}",
  "database": "${POSTGRES_DB}",
  "started_at": "${started_at}",
  "completed_at": "${completed_at}",
  "filename": "${filename}",
  "size_bytes": ${size_bytes},
  "retention_days": ${RETENTION_DAYS},
  "interval_hours": ${INTERVAL_HOURS},
  "message": "${message}"
}
EOF

  mv "${temporary_file}" "${STATUS_FILE}"
}

perform_backup() {
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
  filename="${POSTGRES_DB}_${timestamp}.dump"
  target="${BACKUP_DIR}/${filename}"

  write_status \
    "running" \
    "${started_at}" \
    "" \
    "${filename}" \
    0 \
    "Backup is running"

  echo "[backup] Starting PostgreSQL backup: ${filename}"

  if pg_dump \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file="${target}"; then

    completed_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    size_bytes="$(wc -c < "${target}" | tr -d ' ')"

    echo "[backup] Validating archive: ${filename}"

    if pg_restore --list "${target}" >/dev/null 2>&1; then
      ln -sfn "${filename}" "${BACKUP_DIR}/latest.dump"

      find "${BACKUP_DIR}" \
        -type f \
        -name "*.dump" \
        -mtime "+${RETENTION_DAYS}" \
        -delete

      write_status \
        "success" \
        "${started_at}" \
        "${completed_at}" \
        "${filename}" \
        "${size_bytes}" \
        "Backup completed and archive validation passed"

      echo "[backup] Completed and validated: ${filename} (${size_bytes} bytes)"
    else
      rm -f "${target}"

      write_status \
        "failed" \
        "${started_at}" \
        "${completed_at}" \
        "${filename}" \
        0 \
        "Backup archive validation failed"

      echo "[backup] Validation failed: ${filename}" >&2
    fi
  else
    completed_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    rm -f "${target}"

    write_status \
      "failed" \
      "${started_at}" \
      "${completed_at}" \
      "${filename}" \
      0 \
      "PostgreSQL backup failed"

    echo "[backup] Failed: ${filename}" >&2
  fi
}

trap 'echo "[backup] Shutdown signal received"; exit 0' INT TERM

while true; do
  perform_backup

  sleep_seconds=$((INTERVAL_HOURS * 3600))
  echo "[backup] Next backup in ${INTERVAL_HOURS} hour(s)"
  sleep "${sleep_seconds}" &
  wait $!
done
