#!/bin/sh
set -eu
while true; do
  python -m app.modules.workforce.audit_archiver
  sleep "${WORM_INTERVAL_SECONDS:-86400}"
done
