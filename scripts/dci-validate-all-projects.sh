#!/usr/bin/env bash
# Validate DCI isolation + trees across all Cursor projects in PycharmProjects.
set -uo pipefail

SOURCE="${DCI_PROPAGATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"
REG="${SOURCE}/.cursor/dci/projects.registry"

PASS=0
FAIL=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1 — $2"; FAIL=$((FAIL + 1)); }

check_project() {
  local path="$1" pid="$2"
  local dci="${path}/scripts/dci-vector.sh"
  [[ -x "${dci}" ]] || dci="bash ${path}/scripts/dci-vector.sh"
  local out err rc
  set +e
  out="$(${dci} windows 2>&1)"
  rc=$?
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    fail "${pid}-windows" "exit ${rc}"
    return
  fi
  if ! echo "${out}" | grep -q "project: ${pid}"; then
    fail "${pid}-windows" "missing project header"
    return
  fi
  if ! echo "${out}" | grep -q "name: «"; then
    fail "${pid}-windows" "missing name/desc format"
    return
  fi
  pass "${pid}-windows"

  set +e
  out="$(${dci} projects 2>&1)"
  rc=$?
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    fail "${pid}-projects" "exit ${rc}"
    return
  fi
  if ! echo "${out}" | grep -q "projects:"; then
    fail "${pid}-projects" "missing projects tree"
    return
  fi
  if ! echo "${out}" | grep -q "${pid}"; then
    fail "${pid}-projects" "current project not in tree"
    return
  fi
  pass "${pid}-projects"
}

echo "=== DCI multi-project validate $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# Shared DB namespace isolation (gp_dq sync must not wipe de_matrix)
GP_PY="${SOURCE}/.venv/bin/python"
DM="${ROOT}/de_matrix"
if [[ -x "${GP_PY}" && -d "${DM}/.cursor" ]]; then
  set +e
  env DCI_PROJECT_ID=de_matrix "${GP_PY}" "${DM}/scripts/dci_vector_sync.py" sync --migrate >/dev/null 2>&1
  env DCI_PROJECT_ID=gp_dq "${GP_PY}" "${SOURCE}/scripts/dci_vector_sync.py" sync --project --migrate >/dev/null 2>&1
  cnt="$("${GP_PY}" - <<'PY'
import os, psycopg2
conn = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local", connect_timeout=3)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM dci_embeddings WHERE dialog_id LIKE 'de_matrix/%'")
print(cur.fetchone()[0])
conn.close()
PY
)"
  set -e
  if [[ "${cnt:-0}" -gt 0 ]]; then
    pass "TC-ISO-MP-01 de_matrix vectors after gp_dq sync"
  else
    fail "TC-ISO-MP-01" "de_matrix rows missing (cross-project cleanup?)"
  fi
else
  echo "SKIP  TC-ISO-MP-01 — de_matrix or venv unavailable"
fi

while IFS= read -r line; do
  [[ "${line}" =~ ^# ]] && continue
  [[ -z "${line}" ]] && continue
  pid="${line%%|*}"
  path="${line#*|}"
  check_project "${path}" "${pid}"
done < "${REG}"

echo ""
echo "=== SUMMARY: PASS=${PASS} FAIL=${FAIL} ==="
[[ "${FAIL}" -eq 0 ]]
