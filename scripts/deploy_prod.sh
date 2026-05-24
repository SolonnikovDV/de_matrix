#!/usr/bin/env bash
# Full production deploy: infrastructure + app container + proxy + hardening add-ons.
# For local development prefer: deploy.sh + run_app.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

bash "${ROOT_DIR}/scripts/proxy_prepare_tls.sh"
bash "${ROOT_DIR}/scripts/fail2ban_prepare.sh"

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "[deploy_prod] full stack is up"
bash "${ROOT_DIR}/scripts/prod_status.sh"
