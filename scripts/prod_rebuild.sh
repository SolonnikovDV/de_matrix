#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

WITH_VOLUMES=false
SKIP_PULL=false
HOST_DEV=false
for arg in "$@"; do
  case "${arg}" in
    --with-volumes)
      WITH_VOLUMES=true
      ;;
    --skip-pull)
      SKIP_PULL=true
      ;;
    --host-dev)
      HOST_DEV=true
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--with-volumes] [--skip-pull] [--host-dev]"
      echo "  --with-volumes  stop stack with volume removal (data-loss risk)"
      echo "  --skip-pull     do not pull fresh images before rebuild"
      echo "  --host-dev      redeploy infra only, then run app via scripts/run_app.sh"
      exit 1
      ;;
  esac
done

echo "[rebuild] stop existing stack"
DOWN_ARGS=(--remove-orphans)
if [[ "${WITH_VOLUMES}" == "true" ]]; then
  DOWN_ARGS+=(--volumes)
  echo "[rebuild] WARNING: --with-volumes enabled (persistent data will be removed)"
fi
bash "${ROOT_DIR}/scripts/prod_down.sh" "${DOWN_ARGS[@]}"

if [[ "${SKIP_PULL}" != "true" ]]; then
  echo "[rebuild] pull latest images"
  "${COMPOSE[@]}" pull --ignore-pull-failures || true
fi

if [[ "${HOST_DEV}" == "true" ]]; then
  echo "[rebuild] host-dev mode: infrastructure only"
  bash "${ROOT_DIR}/scripts/deploy.sh"
  echo "[rebuild] done (start app: bash scripts/run_app.sh)"
  exit 0
fi

echo "[rebuild] build and start full production stack"
bash "${ROOT_DIR}/scripts/deploy_prod.sh"

echo "[rebuild] done"
