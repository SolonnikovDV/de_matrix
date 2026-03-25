#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DE_MATRIX_DOMAIN:-localhost}"
MAX_BODY="${DE_MATRIX_PROXY_MAX_BODY_SIZE:-16m}"
REQ_RATE="${DE_MATRIX_PROXY_RATE_LIMIT_RPS:-20r/s}"
REQ_BURST="${DE_MATRIX_PROXY_RATE_LIMIT_BURST:-40}"
CONN_LIMIT="${DE_MATRIX_PROXY_CONN_LIMIT_PER_IP:-30}"
IP_WHITELIST="${DE_MATRIX_PROXY_IP_WHITELIST:-}"
IP_BLACKLIST="${DE_MATRIX_PROXY_IP_BLACKLIST:-}"

export DOMAIN MAX_BODY REQ_RATE REQ_BURST CONN_LIMIT

if [[ ! -f /etc/nginx/certs/fullchain.pem || ! -f /etc/nginx/certs/privkey.pem ]]; then
  echo "TLS certificate files not found in /etc/nginx/certs."
  echo "Run scripts/proxy_prepare_tls.sh first."
  exit 1
fi

WHITELIST_CONF="/tmp/ip-whitelist.conf"
BLACKLIST_CONF="/tmp/ip-blacklist.conf"
: > "${WHITELIST_CONF}"
: > "${BLACKLIST_CONF}"

append_ip_rules() {
  local raw="$1"
  local out_file="$2"
  local item trimmed
  IFS=',' read -ra items <<< "${raw}"
  for item in "${items[@]}"; do
    trimmed="$(echo "${item}" | xargs)"
    [[ -z "${trimmed}" ]] && continue
    echo "${trimmed} 1;" >> "${out_file}"
  done
}

append_ip_rules "${IP_WHITELIST}" "${WHITELIST_CONF}"
append_ip_rules "${IP_BLACKLIST}" "${BLACKLIST_CONF}"

RUNTIME_NGINX_CONF="/tmp/nginx.conf"
envsubst '$DOMAIN $MAX_BODY $REQ_RATE $REQ_BURST $CONN_LIMIT' \
  < /etc/nginx/templates/nginx.conf.template \
  > "${RUNTIME_NGINX_CONF}"

exec nginx -c "${RUNTIME_NGINX_CONF}" -g 'daemon off;'
