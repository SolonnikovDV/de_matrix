#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[prod] compose services"
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

echo
echo "[prod] quick endpoints (from host)"
HTTP_PORT="${DE_MATRIX_PROXY_HTTP_PORT:-80}"
HTTPS_PORT="${DE_MATRIX_PROXY_HTTPS_PORT:-443}"
ADMIN_PORT="${DE_MATRIX_ADMIN_UI_PORT:-19000}"
MAIL_UI_PORT="${DE_MATRIX_MAIL_UI_PORT:-18025}"
PUBLIC_DOMAIN="${DE_MATRIX_DOMAIN:-localhost}"
if [[ "${HTTPS_PORT}" == "443" ]]; then
  APP_LOCAL_URL="https://localhost"
  APP_PUBLIC_URL="https://${PUBLIC_DOMAIN}"
else
  APP_LOCAL_URL="https://localhost:${HTTPS_PORT}"
  APP_PUBLIC_URL="https://${PUBLIC_DOMAIN}:${HTTPS_PORT}"
fi

echo "app (local):           ${APP_LOCAL_URL}"
echo "app (external users):  ${APP_PUBLIC_URL}"
if [[ "${PUBLIC_DOMAIN}" == "localhost" || "${PUBLIC_DOMAIN}" == "127.0.0.1" ]]; then
  echo "hint: set DE_MATRIX_DOMAIN to public host/domain for external access"
fi
echo "proxy-health http:  http://localhost:${HTTP_PORT}/proxy-health"
echo "proxy-health https: https://localhost:${HTTPS_PORT}/proxy-health"
echo "admin ui (local only): http://127.0.0.1:${ADMIN_PORT}"
echo "mail ui (local only):  http://127.0.0.1:${MAIL_UI_PORT}"
