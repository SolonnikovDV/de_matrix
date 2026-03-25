#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

bash "${ROOT_DIR}/scripts/proxy_prepare_tls.sh"
bash "${ROOT_DIR}/scripts/fail2ban_prepare.sh"

# Unified startup: base services + hardened/monitoring add-ons.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "[up] full stack is up"
bash "${ROOT_DIR}/scripts/prod_status.sh"
