#!/usr/bin/env bash
# Deploy infrastructure dependencies only (PostgreSQL, MongoDB, Mailpit).
# Application process is started separately via: bash scripts/run_app.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml)

echo "[deploy] starting infrastructure: postgres, mongo, smtp"
"${COMPOSE[@]}" up -d postgres mongo smtp

echo "[deploy] waiting for health checks"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U dematrix -d dematrix >/dev/null 2>&1 \
    && "${COMPOSE[@]}" exec -T mongo mongosh --eval "db.adminCommand('ping').ok" --quiet >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo
echo "[deploy] infrastructure is up"
echo "postgres: 127.0.0.1:15432 (or DE_MATRIX_POSTGRES_PORT from .env)"
echo "mongo:    127.0.0.1:27018 (or DE_MATRIX_MONGO_PORT from .env)"
echo "mailpit:  http://127.0.0.1:18025"
echo
echo "Next: bash scripts/run_app.sh"
