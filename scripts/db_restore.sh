#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-}"
if [[ -z "${BACKUP_DIR}" ]]; then
  echo "Usage: $0 <backup_dir>"
  exit 1
fi

if [[ ! -f "${BACKUP_DIR}/postgres.sql" || ! -f "${BACKUP_DIR}/mongo.archive" ]]; then
  echo "Backup files not found in ${BACKUP_DIR}"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

if ! docker compose ps >/dev/null 2>&1; then
  echo "docker compose is not available for this project"
  exit 1
fi

docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U dematrix -d dematrix -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
cat "${BACKUP_DIR}/postgres.sql" | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U dematrix -d dematrix
cat "${BACKUP_DIR}/mongo.archive" | docker compose exec -T mongo mongorestore --archive --drop

echo "Restore completed from ${BACKUP_DIR}"

