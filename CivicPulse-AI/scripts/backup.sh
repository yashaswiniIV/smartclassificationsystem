#!/bin/sh
# Nightly Postgres backup → ./backups (rotate after 14 days).
# Cron (on the host):  0 2 * * *  /path/to/scripts/backup.sh >> /var/log/civicpulse-backup.log 2>&1
# For offsite durability, sync ./backups to object storage (R2/S3) after dumping.
set -e

PROJECT="${COMPOSE_PROJECT:-civicpulse-prod}"
OUT_DIR="$(dirname "$0")/../backups"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$OUT_DIR/civicpulse-$STAMP.sql.gz"

CONTAINER="$(docker ps --filter "name=${PROJECT}-postgres" --format '{{.Names}}' | head -n1)"
if [ -z "$CONTAINER" ]; then
  echo "postgres container not found for project $PROJECT" >&2
  exit 1
fi

docker exec "$CONTAINER" pg_dump -U "${POSTGRES_USER:-civicpulse}" "${POSTGRES_DB:-civicpulse}" \
  | gzip > "$FILE"
echo "wrote $FILE"

# rotate: keep the last 14 days
find "$OUT_DIR" -name 'civicpulse-*.sql.gz' -mtime +14 -delete
