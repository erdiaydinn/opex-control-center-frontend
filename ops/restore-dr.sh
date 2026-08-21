#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "Kullanım: restore-dr.sh /backups/opex_workforce_YYYYMMDDTHHMMSSZ.dump" >&2
  exit 2
fi
sha256sum -c "$1.sha256"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$DATABASE_URL" "$1"
echo "Geri yükleme tamamlandı; uygulama sağlık ve audit zinciri kontrolünü çalıştırın."
