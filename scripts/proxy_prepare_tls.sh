#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
TLS_MODE="${DE_MATRIX_TLS_MODE:-selfsigned}"            # selfsigned | provided
DOMAIN="${DE_MATRIX_DOMAIN:-localhost}"
DAYS="${DE_MATRIX_TLS_SELF_SIGNED_DAYS:-365}"

if [[ -f "${ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      DE_MATRIX_TLS_MODE) TLS_MODE="${value}" ;;
      DE_MATRIX_DOMAIN) DOMAIN="${value}" ;;
      DE_MATRIX_TLS_SELF_SIGNED_DAYS) DAYS="${value}" ;;
    esac
  done < "${ENV_FILE}"
fi

LIVE_DIR="${ROOT_DIR}/proxy/certs/live"
PROVIDED_DIR="${ROOT_DIR}/proxy/certs/provided"
mkdir -p "${LIVE_DIR}" "${PROVIDED_DIR}"

if [[ "${TLS_MODE}" == "selfsigned" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required for self-signed cert generation"
    exit 1
  fi
  echo "[tls] generating self-signed cert for CN=${DOMAIN}, days=${DAYS}"
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout "${LIVE_DIR}/privkey.pem" \
    -out "${LIVE_DIR}/fullchain.pem" \
    -days "${DAYS}" \
    -subj "/CN=${DOMAIN}"
  chmod 600 "${LIVE_DIR}/privkey.pem"
  chmod 644 "${LIVE_DIR}/fullchain.pem"
  echo "[tls] self-signed cert generated in ${LIVE_DIR}"
elif [[ "${TLS_MODE}" == "provided" ]]; then
  if [[ ! -f "${PROVIDED_DIR}/fullchain.pem" || ! -f "${PROVIDED_DIR}/privkey.pem" ]]; then
    echo "[tls] provided mode expects files:"
    echo "  ${PROVIDED_DIR}/fullchain.pem"
    echo "  ${PROVIDED_DIR}/privkey.pem"
    exit 1
  fi
  cp "${PROVIDED_DIR}/fullchain.pem" "${LIVE_DIR}/fullchain.pem"
  cp "${PROVIDED_DIR}/privkey.pem" "${LIVE_DIR}/privkey.pem"
  chmod 600 "${LIVE_DIR}/privkey.pem"
  chmod 644 "${LIVE_DIR}/fullchain.pem"
  echo "[tls] provided cert copied to ${LIVE_DIR}"
else
  echo "Unknown DE_MATRIX_TLS_MODE=${TLS_MODE} (supported: selfsigned, provided)"
  exit 1
fi

echo "[tls] done"
