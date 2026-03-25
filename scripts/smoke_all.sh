#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

BACKUP_ROOT="${ROOT_DIR}/data/db_backups/smoke-all"
ROLLBACK=false
PY_RUN=""

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PY_RUN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY_RUN="python3"
elif command -v python >/dev/null 2>&1; then
  PY_RUN="python"
else
  echo "No Python interpreter found (need .venv/bin/python or python3/python)"
  exit 1
fi

for arg in "$@"; do
  case "${arg}" in
    --rollback)
      ROLLBACK=true
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--rollback]"
      exit 1
      ;;
  esac
done

BACKUP_PATH=""

restore_if_needed() {
  if [[ "${ROLLBACK}" == "true" && -n "${BACKUP_PATH}" && -d "${BACKUP_PATH}" ]]; then
    echo "[smoke-all] restoring backup: ${BACKUP_PATH}"
    bash "${ROOT_DIR}/scripts/db_restore.sh" "${BACKUP_PATH}"
  fi
}

echo "[smoke-all] ensuring docker stack is up"
bash "${ROOT_DIR}/scripts/proxy_prepare_tls.sh"
docker compose up -d

echo "[smoke-all] waiting for app container health"
for i in $(seq 1 60); do
  app_state="$(docker inspect --format '{{.State.Status}}' de-matrix-app 2>/dev/null || true)"
  app_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' de-matrix-app 2>/dev/null || true)"
  if [[ "${app_state}" == "running" && ( "${app_health}" == "healthy" || "${app_health}" == "none" ) ]]; then
    break
  fi
  if [[ "${i}" == "60" ]]; then
    echo "[smoke-all] app failed to become healthy"
    docker compose ps || true
    docker compose logs --no-color --tail=200 app || true
    exit 1
  fi
  sleep 2
done

if [[ "${ROLLBACK}" == "true" ]]; then
  echo "[smoke-all] creating backup before tests"
  mkdir -p "${BACKUP_ROOT}"
  bash "${ROOT_DIR}/scripts/db_backup.sh" "${BACKUP_ROOT}"
  BACKUP_PATH="$(ls -1d "${BACKUP_ROOT}"/* | sort | tail -n 1)"
  trap restore_if_needed EXIT
fi

echo "[smoke-all] db init"
if docker compose exec -T postgres psql -U dematrix -d dematrix < "${ROOT_DIR}/migrations/001_initial.sql"; then
  echo "[smoke-all] schema applied via psql migration"
else
  echo "[smoke-all] psql migration failed, fallback to app db_init.py"
  docker compose exec -T app python scripts/db_init.py
fi

echo "[smoke-all] db smoke check"
docker compose exec -T app python scripts/db_smoke_check.py

echo "[smoke-all] autoscale regression"
docker compose exec -T app python scripts/autoscale_regression_check.py

echo "[smoke-all] e2e merge-modes approval workflow"
docker compose exec -T app python scripts/e2e_merge_modes_check.py

echo "[smoke-all] all checks passed"
