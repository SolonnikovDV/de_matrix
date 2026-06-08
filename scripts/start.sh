#!/usr/bin/env bash
# =============================================================================
# One-click dev startup — self-healing, zero port conflicts.
#
# Port strategy:
#   docker-compose.yml uses "0:PORT" — Docker assigns a FREE host port
#   automatically (no manual conflict detection needed).
#   After containers are healthy, start.sh discovers the actual assigned ports
#   via `docker compose port`, exports them as env vars, and hands off to
#   python app.py. env_bootstrap.py then rewrites the DB URL accordingly.
#
# Flow:
#   1.  .env load  (safe parser, bash 3.2+)
#   2.  Docker daemon check
#   3.  Prod-stack teardown if running  (frees compose-project state)
#   4.  Infra-only startup  (postgres, mongo, smtp)
#   5.  Health gate  (docker exec — reliable internal check)
#   6.  Port discovery  (docker compose port → actual OS-assigned ports)
#   7.  Python venv + pip  (hash-gated)
#   8.  Launch  python app.py
#
# Usage:
#   bash scripts/start.sh           # normal dev start
#   bash scripts/start.sh --debug   # extra args forwarded to app.py
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# ── helpers ──────────────────────────────────────────────────────────────────
_log()  { printf '\033[0;36m[start]\033[0m %s\n' "$*"; }
_ok()   { printf '\033[0;32m[start] ✓\033[0m %s\n' "$*"; }
_warn() { printf '\033[0;33m[start] !\033[0m %s\n' "$*"; }
_fail() { printf '\033[0;31m[start] ✗\033[0m %s\n' "$*" >&2; exit 1; }

# Discover the host port Docker assigned for svc:container_port.
# Handles all output formats: 0.0.0.0:PORT, 127.0.0.1:PORT, [::]:PORT
# Uses `awk -F: '{print $NF}'` — always takes the last colon-delimited field.
_discover_port() {
  local svc=$1 internal=$2
  local raw
  raw="$("${COMPOSE[@]}" port "${svc}" "${internal}" 2>/dev/null)" || true
  if [[ -z "${raw}" ]]; then
    echo ""
    return 1
  fi
  echo "${raw}" | awk -F: '{print $NF}'
}

_req_hash() {
  python3 -c \
    "import hashlib,sys; print(hashlib.md5(open(sys.argv[1],'rb').read()).hexdigest())" \
    "${ROOT_DIR}/requirements.txt" 2>/dev/null || echo "unknown"
}

# Safe .env loader — never executes the file.
# Always exports from .env (source of truth), bash 3.2+ compatible.
_load_env() {
  local file=$1 line key val
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" || "${line}" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    case "${val}" in
      '"'*'"') val="${val#\"}"; val="${val%\"}" ;;
      "'"*"'") val="${val#\'}"; val="${val%\'}" ;;
    esac
    export "${key}=${val}"
  done < "${file}"
}

# ── 1. .env ──────────────────────────────────────────────────────────────────
if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  if [[ -f "${ROOT_DIR}/.env.example" ]]; then
    _warn ".env not found — copying .env.example  (edit credentials before production!)"
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  else
    _fail ".env missing and .env.example not found"
  fi
fi

_load_env "${ROOT_DIR}/.env"
[[ -f "${ROOT_DIR}/.env.local" ]] && _load_env "${ROOT_DIR}/.env.local"
_ok ".env loaded"

# ── 2. Docker daemon ──────────────────────────────────────────────────────────
_log "checking Docker daemon..."
docker info >/dev/null 2>&1 || _fail "Docker daemon not running — start Docker Desktop and retry."
_ok "Docker daemon is up"

COMPOSE_DEV=(docker compose -f "${ROOT_DIR}/docker-compose.yml")
COMPOSE_PROD=(docker compose \
  -f "${ROOT_DIR}/docker-compose.yml" \
  -f "${ROOT_DIR}/docker-compose.prod.yml")
COMPOSE=("${COMPOSE_DEV[@]}")

# ── 3. Prod-stack teardown ────────────────────────────────────────────────────
# When the full production stack (de-matrix-app) is running, postgres/mongo
# are owned by the prod compose-project. Containers in that project context
# won't expose host ports correctly for host-dev mode.
# Full `compose down` wipes project state → fresh infra-only up works cleanly.
_log "checking for production stack..."
if docker ps --format "{{.Names}}" 2>/dev/null | grep -qx "de-matrix-app"; then
  _warn "Production stack running — stopping for dev-infra mode (data preserved)"
  _warn "Restart production anytime:  bash scripts/deploy_prod.sh"
  "${COMPOSE_PROD[@]}" down --remove-orphans 2>/dev/null \
    || "${COMPOSE_DEV[@]}"  down --remove-orphans 2>/dev/null \
    || true
  _ok "prod stack stopped"
fi

# ── 4. Infra-only startup ─────────────────────────────────────────────────────
# Always run `compose up` — Docker detects config changes (networks, ports, image)
# and recreates only affected containers. Safe and idempotent.
_log "reconciling infra containers (postgres, mongo, smtp)..."
"${COMPOSE[@]}" up -d --remove-orphans postgres mongo smtp
_ok "infra containers reconciled"

# ── 5. Health gate ────────────────────────────────────────────────────────────
_log "waiting for postgres + mongo to be healthy (up to 120 s)..."
DEADLINE=$(( $(date +%s) + 120 ))
while true; do
  PG_UP=false; MG_UP=false
  "${COMPOSE[@]}" exec -T postgres pg_isready -U dematrix -d dematrix \
    >/dev/null 2>&1 && PG_UP=true
  "${COMPOSE[@]}" exec -T mongo mongosh \
    --eval "db.adminCommand('ping').ok" --quiet >/dev/null 2>&1 && MG_UP=true
  [[ "${PG_UP}" == true && "${MG_UP}" == true ]] && break
  (( $(date +%s) >= DEADLINE )) && \
    _fail "infra not healthy after 120 s — check: docker compose -f docker-compose.yml logs --tail=50"
  sleep 3
done
_ok "postgres and mongo are healthy"

# ── 6. Port discovery ─────────────────────────────────────────────────────────
# Read the host ports that Docker actually assigned (from "0:PORT" bindings).
# Export them so env_bootstrap.py can rewrite the DB URL correctly.
_log "discovering assigned host ports..."

PG_PORT="$(_discover_port postgres 5432)"
MONGO_PORT="$(_discover_port mongo 27017)"
SMTP_PORT="$(_discover_port smtp 1025)"
MAIL_UI_PORT="$(_discover_port smtp 8025)"

[[ -z "${PG_PORT}"    || "${PG_PORT}"    == "0" ]] && \
  _fail "postgres host port is '${PG_PORT:-empty}' — Docker Desktop failed to bind port. Check docker-compose.yml network config."
[[ -z "${MONGO_PORT}" || "${MONGO_PORT}" == "0" ]] && \
  _fail "mongo host port is '${MONGO_PORT:-empty}' — Docker Desktop failed to bind port. Check docker-compose.yml network config."

export DE_MATRIX_POSTGRES_PORT="${PG_PORT}"
export DE_MATRIX_MONGO_PORT="${MONGO_PORT}"
[[ -n "${SMTP_PORT}"    ]] && export DE_MATRIX_SMTP_PORT="${SMTP_PORT}"
[[ -n "${MAIL_UI_PORT}" ]] && export DE_MATRIX_MAIL_UI_PORT="${MAIL_UI_PORT}"

_ok "ports discovered  (pg=${PG_PORT}  mongo=${MONGO_PORT}  smtp=${SMTP_PORT:-?}  mailui=${MAIL_UI_PORT:-?})"

# ── 7. Python venv ────────────────────────────────────────────────────────────
if [[ ! -d "${ROOT_DIR}/.venv" ]]; then
  _log "creating virtual environment..."
  python3 -m venv "${ROOT_DIR}/.venv"
  _ok ".venv created"
fi
# shellcheck disable=SC1091
source "${ROOT_DIR}/.venv/bin/activate"
_ok "venv activated  ($(python --version))"

# ── 8. Dependencies  (hash-gated — fast on repeat runs) ──────────────────────
REQ_HASH_FILE="${ROOT_DIR}/.venv/.req_hash"
CURRENT_HASH="$(_req_hash)"
if [[ ! -f "${REQ_HASH_FILE}" || "$(cat "${REQ_HASH_FILE}")" != "${CURRENT_HASH}" ]]; then
  _log "requirements.txt changed — installing dependencies..."
  pip install -q -r "${ROOT_DIR}/requirements.txt"
  echo "${CURRENT_HASH}" > "${REQ_HASH_FILE}"
  _ok "dependencies updated"
else
  _ok "dependencies up to date"
fi

# ── 9. Launch ────────────────────────────────────────────────────────────────
echo
_ok "launching app  (pg=${PG_PORT}  mongo=${MONGO_PORT})"
echo
exec python app.py "$@"
