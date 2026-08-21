#!/bin/sh
set -eu

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="/backups/opex_workforce_${timestamp}.dump"
pg_dump --format=custom --compress=9 --no-owner --no-acl --file="$target" "$DATABASE_URL"
sha256sum "$target" > "${target}.sha256"
find /backups -type f -mtime "+${BACKUP_RETENTION_DAYS:-35}" -delete
echo "Backup doğrulandı: $target"
