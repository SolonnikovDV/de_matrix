#!/usr/bin/env bash
# DCI vector store helper v9: windows + project EV namespaces + local embed server
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/.cursor/dci/docker-compose.yml"
ENV_FILE="${ROOT}/.cursor/dci/dci.env"
SYNC_PY="${ROOT}/scripts/dci_vector_sync.py"
EMBED_PY="${ROOT}/scripts/dci_embed_server.py"
PY="${ROOT}/.venv/bin/python"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
elif [[ -f "${ROOT}/.cursor/dci/dci.env.example" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/.cursor/dci/dci.env.example"
  set +a
fi

embed_home() {
  local reg="${ROOT}/.cursor/dci/projects.registry"
  if [[ -f "${reg}" ]]; then
    local line
    line="$(grep -E '^gp_dq\|' "${reg}" | head -1 || true)"
    if [[ -n "${line}" ]]; then
      echo "${line#*|}"
      return 0
    fi
  fi
  echo "${ROOT}"
}

EMBED_HOME="$(embed_home)"
EMBED_PID_FILE="${EMBED_HOME}/.cursor/dci/.embed_server.pid"
EMBED_LOG="${EMBED_HOME}/.cursor/dci/embed_server.log"
EMBED_PORT="${DCI_EMBED_PORT:-18081}"
EMBED_MODEL="${DCI_EMBED_MODEL:-intfloat/multilingual-e5-small}"

tei_ok() {
  "${PY}" "${SYNC_PY}" status 2>/dev/null | grep -q "tei: ok"
}

embed_start() {
  mkdir -p "$(dirname "${EMBED_PID_FILE}")"
  if tei_ok; then
    echo "Embed server: already healthy on :${EMBED_PORT}"
    return 0
  fi
  if [[ -f "${EMBED_PID_FILE}" ]]; then
    local old_pid
    old_pid="$(cat "${EMBED_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      echo "Embed server: stale pid ${old_pid}, waiting for health..."
    else
      rm -f "${EMBED_PID_FILE}"
    fi
  fi
  if ! "${PY}" -c "import sentence_transformers" 2>/dev/null; then
    echo "Installing sentence-transformers into ${ROOT}/.venv ..."
    "${ROOT}/.venv/bin/pip" install -q "numpy<2" sentence-transformers
  fi
  echo "Starting embed server (${EMBED_MODEL}) on :${EMBED_PORT}..."
  nohup "${PY}" "${EMBED_PY}" --host 127.0.0.1 --port "${EMBED_PORT}" --model "${EMBED_MODEL}" \
    >>"${EMBED_LOG}" 2>&1 &
  echo $! >"${EMBED_PID_FILE}"
  for _ in $(seq 1 120); do
    if tei_ok; then
      echo "Embed server: ok (pid $(cat "${EMBED_PID_FILE}"))"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: embed server failed to become healthy; see ${EMBED_LOG}" >&2
  return 1
}

embed_stop() {
  if [[ ! -f "${EMBED_PID_FILE}" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "${EMBED_PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    echo "Embed server stopped (pid ${pid})"
  fi
  rm -f "${EMBED_PID_FILE}"
}

cmd="${1:-status}"
shift || true

case "${cmd}" in
  up)
    docker compose -f "${COMPOSE_FILE}" up -d dci-pgvector
    echo "Waiting for pgvector health..."
    for _ in $(seq 1 45); do
      if "${PY}" "${SYNC_PY}" status 2>/dev/null | grep -q "pgvector: ok"; then
        break
      fi
      sleep 2
    done
    embed_start
    "${PY}" "${SYNC_PY}" sync --migrate --all --reembed "$@"
    ;;
  down)
    embed_stop
    docker compose -f "${COMPOSE_FILE}" down "$@"
    ;;
  status)
    docker compose -f "${COMPOSE_FILE}" ps 2>/dev/null || true
    if [[ -f "${EMBED_PID_FILE}" ]]; then
      echo "embed_pid: $(cat "${EMBED_PID_FILE}" 2>/dev/null || echo '?') (${EMBED_PID_FILE})"
    fi
    "${PY}" "${SYNC_PY}" status
    ;;
  sync)
    "${PY}" "${SYNC_PY}" sync --migrate "$@"
    ;;
  migrate)
    "${PY}" "${SYNC_PY}" migrate "$@"
    ;;
  export)
    "${PY}" "${SYNC_PY}" export "$@"
    ;;
  import)
    "${PY}" "${SYNC_PY}" import --source "${1:?bundle path required}" "${@:2}"
    ;;
  lookup)
    "${PY}" "${SYNC_PY}" lookup --query "${1:?query required}" "${@:2}"
    ;;
  catalog)
    mode="all"
    if [[ "${1:-}" == "--branches" ]]; then
      mode="branches"
      shift
    elif [[ "${1:-}" == "--windows" ]]; then
      mode="windows"
      shift
    fi
    "${PY}" "${SYNC_PY}" catalog --mode "${mode}" "$@"
    ;;
  window-new)
    "${PY}" "${SYNC_PY}" window-new --summary "${*:-New dialog window}"
    ;;
  restore)
    wid="${1:?window id required, e.g. DW-001}"
    shift || true
    "${PY}" "${SYNC_PY}" restore --window "${wid}" --migrate "$@"
    ;;
  compress)
    "${PY}" "${SYNC_PY}" compress "$@"
    ;;
  materialize)
    "${PY}" "${SYNC_PY}" materialize "$@"
    ;;
  validate)
    "${PY}" "${SYNC_PY}" validate "$@"
    ;;
  doctor)
    "${PY}" "${SYNC_PY}" doctor "$@"
    ;;
  windows)
    "${PY}" "${SYNC_PY}" windows "$@"
    ;;
  projects)
    "${PY}" "${SYNC_PY}" projects "$@"
    ;;
  restore-new)
    "${PY}" "${SYNC_PY}" user-restore --window "новое" --summary "${*:-New dialog window}"
    ;;
  *)
    echo "Usage: $0 {compress|materialize|validate|doctor|windows|projects|restore|restore-new|up|down|status|...}" >&2
    exit 1
    ;;
esac
