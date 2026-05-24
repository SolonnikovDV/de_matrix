#!/usr/bin/env bash
# Run application entrypoint (python app.py) on host.
# Requires infrastructure from: bash scripts/deploy.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  echo "[run_app] .env not found. Copy from .env.example and adjust credentials."
  exit 1
fi

if [[ -d "${ROOT_DIR}/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.venv/bin/activate"
fi

if ! docker compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  echo "[run_app] postgres container is not running. Start infra first:"
  echo "  bash scripts/deploy.sh"
  exit 1
fi

echo "[run_app] starting python app.py (host runtime)"
exec python app.py "$@"
