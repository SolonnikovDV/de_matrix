#!/usr/bin/env bash
set -euo pipefail

TS="$(date +"%Y-%m-%d_%H-%M-%S")"
OUT_DIR="${1:-data/db_backups}/${TS}"
mkdir -p "${OUT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

if ! docker compose ps >/dev/null 2>&1; then
  echo "docker compose is not available for this project"
  exit 1
fi

docker compose exec -T postgres pg_dump -U dematrix -d dematrix > "${OUT_DIR}/postgres.sql"
docker compose exec -T mongo mongodump --archive > "${OUT_DIR}/mongo.archive"

cat > "${OUT_DIR}/README.txt" <<EOF
Backup timestamp: ${TS}
RPO: up to interval between backups
RTO: depends on database size; restore in order postgres.sql -> mongo.archive
Restore command:
  ./scripts/db_restore.sh "${OUT_DIR}"
EOF

echo "Backups created in ${OUT_DIR}"

