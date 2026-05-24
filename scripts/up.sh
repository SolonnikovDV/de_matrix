#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[up] alias -> deploy_prod.sh (full docker stack)"
bash "${ROOT_DIR}/scripts/deploy_prod.sh"
