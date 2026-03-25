#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
TPL="${ROOT_DIR}/security/fail2ban/jail.local.template"
OUT="${ROOT_DIR}/security/fail2ban/jail.local"

DE_MATRIX_FAIL2BAN_BANTIME="${DE_MATRIX_FAIL2BAN_BANTIME:-2h}"
DE_MATRIX_FAIL2BAN_FINDTIME="${DE_MATRIX_FAIL2BAN_FINDTIME:-10m}"
DE_MATRIX_FAIL2BAN_MAXRETRY="${DE_MATRIX_FAIL2BAN_MAXRETRY:-30}"

if [[ -f "${ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      DE_MATRIX_FAIL2BAN_BANTIME) DE_MATRIX_FAIL2BAN_BANTIME="${value}" ;;
      DE_MATRIX_FAIL2BAN_FINDTIME) DE_MATRIX_FAIL2BAN_FINDTIME="${value}" ;;
      DE_MATRIX_FAIL2BAN_MAXRETRY) DE_MATRIX_FAIL2BAN_MAXRETRY="${value}" ;;
    esac
  done < "${ENV_FILE}"
fi

export DE_MATRIX_FAIL2BAN_BANTIME
export DE_MATRIX_FAIL2BAN_FINDTIME
export DE_MATRIX_FAIL2BAN_MAXRETRY

if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst is required (gettext package)"
  exit 1
fi

envsubst < "${TPL}" > "${OUT}"
echo "[fail2ban] generated ${OUT}"
