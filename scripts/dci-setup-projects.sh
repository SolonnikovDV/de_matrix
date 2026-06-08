#!/usr/bin/env bash
# One-shot DCI setup for all Cursor projects: TEI env, window themes, venv, gitignore.
set -euo pipefail

SOURCE="${DCI_PROPAGATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"

win_name() {
  case "$1" in
    gp_dq) echo "Greenplum DQ" ;;
    db-graph-scanner) echo "DB Graph Scanner" ;;
    dbscaner) echo "DB Scanner" ;;
    de_matrix) echo "DE Matrix" ;;
    dockyard) echo "Dockyard" ;;
    greenplum_releases) echo "Greenplum Releases" ;;
    overhead_analyzer) echo "Overhead Analyzer" ;;
    proxy_mart_ui) echo "Proxy Mart UI" ;;
    proxy_vpn) echo "Proxy VPN" ;;
    *) echo "$1" ;;
  esac
}

win_desc() {
  case "$1" in
    gp_dq) echo "Качество данных Greenplum: SQL-проверки, UAT, mart и спец-DQ сценарии" ;;
    db-graph-scanner) echo "Сканирование схем БД и построение графа объектов" ;;
    dbscaner) echo "Утилиты сканирования и инспекции баз данных" ;;
    de_matrix) echo "Матрица компетенций data engineering и аттестация" ;;
    dockyard) echo "Основное рабочее окно проекта Dockyard" ;;
    greenplum_releases) echo "Релизы и поставка Greenplum: версии, деплой, changelog" ;;
    overhead_analyzer) echo "GPA: анализ overhead, web-приложение и агенты" ;;
    proxy_mart_ui) echo "UI для proxy mart: интерфейс и интеграции" ;;
    proxy_vpn) echo "Proxy VPN: инфраструктура, конфигурация и мониторинг" ;;
    *) echo "Primary dialog window for $1" ;;
  esac
}

DCI_GITIGNORE_MARKER="# --- DCI local/runtime (do not publish) ---"
DCI_GITIGNORE_BLOCK="${DCI_GITIGNORE_MARKER}
.cursor/dci/dci.env
.cursor/context/.project_lock
.cursor/context/.dialog_window_lock
.cursor/context/vector_fallback.jsonl
.cursor/context/.compress_snapshot.project.json
.cursor/context/dialogs/**/.compress_snapshot.json
.cursor/context/dialogs/**/dialog_bundle.md
.cursor/context/dialog_bundle.md
.cursor/context/vector_index.meta.md
.cursor/context/dialogs/**/vector_index.meta.md
.cursor/dci/.embed_server.pid
.cursor/dci/embed_server.log"

ensure_gitignore() {
  local target="$1"
  local gi="${target}/.gitignore"
  if [[ -f "${gi}" ]] && grep -qF "${DCI_GITIGNORE_MARKER}" "${gi}" 2>/dev/null; then
    echo "  gitignore: DCI block present"
    return 0
  fi
  if [[ ! -f "${gi}" ]]; then
    cat >"${gi}" <<'HDR'
# Local / generated
.venv/
__pycache__/
*.pyc
.DS_Store

HDR
  fi
  printf '\n%s\n' "${DCI_GITIGNORE_BLOCK}" >>"${gi}"
  echo "  gitignore: appended DCI runtime block"
}

enable_tei_env() {
  local envf="$1" pid="$2"
  mkdir -p "$(dirname "${envf}")"
  if [[ ! -f "${envf}" ]]; then
    cp "${SOURCE}/.cursor/dci/dci.env.example" "${envf}" 2>/dev/null || true
  fi
  python3 - "${envf}" "${pid}" "${ROOT}" <<'PY'
import re, sys
path, pid, projects_root = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read() if __import__("pathlib").Path(path).is_file() else ""
if "DCI_PROJECT_ID=" not in text:
    text += f"\nDCI_PROJECT_ID={pid}\n"
else:
    text = re.sub(r"^DCI_PROJECT_ID=.*$", f"DCI_PROJECT_ID={pid}", text, count=1, flags=re.M)
if "DCI_PROJECTS_ROOT=" not in text:
    text += f"DCI_PROJECTS_ROOT={projects_root}\n"
else:
    text = re.sub(r"^DCI_PROJECTS_ROOT=.*$", f"DCI_PROJECTS_ROOT={projects_root}", text, count=1, flags=re.M)
text = re.sub(r"^#\s*DCI_EMBED_URL=", "DCI_EMBED_URL=", text, count=1, flags=re.M)
text = re.sub(r"^#\s*DCI_EMBED_MODEL=", "DCI_EMBED_MODEL=", text, count=1, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY
  echo "  dci.env: TEI + DCI_PROJECT_ID=${pid} + DCI_PROJECTS_ROOT"
}

sync_projects_registry() {
  local target="$1"
  local reg_src="${SOURCE}/.cursor/dci/projects.registry"
  local reg_dst="${target}/.cursor/dci/projects.registry"
  [[ -f "${reg_src}" ]] || return 0
  if [[ "$(cd "${target}" && pwd)" == "$(cd "${SOURCE}" && pwd)" ]]; then
    echo "  projects.registry: source (skip copy)"
    return 0
  fi
  mkdir -p "$(dirname "${reg_dst}")"
  cp -f "${reg_src}" "${reg_dst}"
  echo "  projects.registry: synced"
}

ensure_venv() {
  local target="$1"
  local venv="${target}/.venv"
  local py="${venv}/bin/python"
  local pip="${venv}/bin/pip"
  if [[ ! -x "${py}" ]]; then
    echo "  venv: creating"
    python3 -m venv "${venv}"
  else
    echo "  venv: exists"
  fi
  if ! "${py}" -c "import psycopg2" 2>/dev/null; then
    echo "  venv: installing psycopg2-binary"
    "${pip}" install -q psycopg2-binary
  else
    echo "  venv: psycopg2 ok"
  fi
  if [[ "$(basename "${target}")" == "gp_dq" ]] && ! "${py}" -c "import sentence_transformers" 2>/dev/null; then
    echo "  venv: installing sentence-transformers (embed server)"
    "${pip}" install -q "numpy<2" sentence-transformers
  elif "${py}" -c "import sentence_transformers" 2>/dev/null; then
    echo "  venv: sentence-transformers ok"
  fi
}

patch_window_theme() {
  local target="$1" pid="$2" name="$3" desc="$4"
  local idx="${target}/.cursor/context/dialogs/DW-001/dialog_index.md"
  local cat="${target}/.cursor/context/project_catalog.md"
  [[ -f "${idx}" ]] || return 0
  python3 - "${idx}" "${name}" "${desc}" "${pid}" <<'PY'
import re, sys
path, name, desc, pid = sys.argv[1:5]
text = open(path, encoding="utf-8").read()
for field, val in [("window_name", name), ("window_description", desc)]:
    if re.search(rf"^{re.escape(field)}:", text, re.M):
        text = re.sub(rf"^{re.escape(field)}:.*$", f"{field}: {val}", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(dialog_window_id: DW-001\n)", rf"\1{field}: {val}\n", text, count=1)
# Q-001 first row
text = re.sub(
    r"(\| Q-001 \| )([^|]+)( \| )",
    lambda m: m.group(1) + desc[:120] + m.group(3),
    text,
    count=1,
)
open(path, "w", encoding="utf-8").write(text)
PY
  if [[ -f "${cat}" ]]; then
    python3 - "${cat}" "${name}" "${desc}" <<'PY'
import re, sys
path, name, desc = sys.argv[1:4]
block = re.search(r"(\| DW-001 \|[^\n]+\n)", open(path, encoding="utf-8").read())
if not block:
    sys.exit(0)
old = block.group(1)
parts = [p.strip() for p in old.strip("|").split("|")]
if len(parts) >= 8:
    parts[3], parts[4] = name, desc
    new = "| " + " | ".join(parts) + " |\n"
    text = open(path, encoding="utf-8").read()
    text = text.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(text)
PY
  fi
  echo "  window: «${name}»"
}

setup_one() {
  local target="$1"
  local pid
  pid="$(basename "${target}")"
  [[ -d "${target}/.cursor" ]] || return 0
  [[ -f "${target}/scripts/dci-vector.sh" ]] || return 0
  echo "=== ${pid} ==="
  ensure_gitignore "${target}"
  sync_projects_registry "${target}"
  enable_tei_env "${target}/.cursor/dci/dci.env" "${pid}"
  ensure_venv "${target}"
  patch_window_theme "${target}" "${pid}" "$(win_name "${pid}")" "$(win_desc "${pid}")"
}

echo "Starting shared DCI stack from ${SOURCE}..."
bash "${SOURCE}/scripts/dci-vector.sh" up || echo "WARN: dci-vector.sh up failed (Docker?)" >&2

while IFS= read -r line; do
  [[ "${line}" =~ ^# ]] && continue
  [[ -z "${line}" ]] && continue
  pid="${line%%|*}"
  path="${line#*|}"
  setup_one "${path}"
done < "${SOURCE}/.cursor/dci/projects.registry"

echo "Done."
