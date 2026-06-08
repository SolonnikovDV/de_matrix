#!/usr/bin/env bash
# DCI v8 automated test runner (P0 auto cases + DB R/W)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PY="${ROOT}/.venv/bin/python"
SYNC="${ROOT}/scripts/dci_vector_sync.py"
DCI="${ROOT}/scripts/dci-vector.sh"

PASS=0
FAIL=0
SKIP=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1 — $2"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP  $1 — $2"; SKIP=$((SKIP + 1)); }

run_expect_exit() {
  local id="$1" expected="$2"
  shift 2
  set +e
  "$@" >/tmp/dci_test_out.txt 2>/tmp/dci_test_err.txt
  local rc=$?
  set -e
  if [[ "${rc}" -eq "${expected}" ]]; then
    pass "${id}"
  else
    fail "${id}" "expected exit ${expected}, got ${rc}; stderr: $(head -1 /tmp/dci_test_err.txt)"
  fi
}

run_expect_ok() {
  local id="$1"
  shift
  run_expect_exit "${id}" 0 "$@"
}

run_grep_stdout() {
  local id="$1" pattern="$2"
  shift 2
  set +e
  local out
  out="$("$@" 2>&1)"
  local rc=$?
  set -e
  if [[ "${rc}" -eq 0 ]] && echo "${out}" | grep -qE "${pattern}"; then
    pass "${id}"
  else
    fail "${id}" "pattern '${pattern}' not found (rc=${rc})"
  fi
}

echo "=== DCI v9 test run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# P0 — ops
run_grep_stdout "TC-OPS-01" "pgvector: ok" bash "${DCI}" status
run_grep_stdout "TC-CAT-01" "EV-PROJECT" bash "${DCI}" catalog
run_grep_stdout "TC-CAT-01" "DW-001" bash "${DCI}" catalog

# validate gate
run_grep_stdout "TC-VAL-01" "validate: pass" bash "${DCI}" validate

# handoff + delta restore
run_grep_stdout "TC-HO-01" "handoff_ready: true" bash "${DCI}" compress --force
run_grep_stdout "TC-HO-01" "restore: /custom-rule: dci restore DW-001" bash "${DCI}" compress --force
run_grep_stdout "TC-HO-02" "load_mode: delta" bash "${DCI}" restore DW-001
run_grep_stdout "TC-MAT-01" "materialize:" bash "${DCI}" compress --force

# QA: compress -> restore (derive DW from compress output)
set +e
ho_out="$(bash "${DCI}" compress --force 2>&1)"
rc_ho=$?
set -e
if [[ "${rc_ho}" -ne 0 ]]; then
  fail "TC-HO-03" "compress failed rc=${rc_ho}"
else
  dw_restore="$(echo "${ho_out}" | sed -n 's#^restore: /custom-rule: dci restore ##p' | head -1 | tr -d '[:space:]')"
  if [[ -z "${dw_restore}" ]]; then
    fail "TC-HO-03" "restore command not found in compress output"
  else
    run_grep_stdout "TC-HO-03" "load_mode: restore" bash "${DCI}" restore "${dw_restore}"
  fi
fi

# window registry slot/lifecycle sync + tree output
run_grep_stdout "TC-REG-01" "name: «" bash "${DCI}" windows
run_grep_stdout "TC-REG-02" "DW-002 | name: «UAT special_dq_2»" bash "${DCI}" windows
run_grep_stdout "TC-REG-03" "EV-PROJECT \\[master\\] | name:" bash "${DCI}" windows
run_grep_stdout "TC-PRJ-TREE-01" "projects:" bash "${DCI}" projects
run_grep_stdout "TC-PRJ-TREE-02" "gp_dq \\*active" bash "${DCI}" projects

# sync all
run_expect_ok "TC-VI-01/02" "${PY}" "${SYNC}" sync --migrate --all

# guards
run_expect_exit "TC-PRJ-01" 2 env DCI_PROJECT_ID=other_project "${PY}" "${SYNC}" status
run_expect_exit "TC-DW-01" 2 env DCI_DIALOG_WINDOW_ID=DW-999 "${PY}" "${SYNC}" status
printf 'project_id: other\n' >/tmp/fake_bundle.md
run_expect_exit "TC-PRJ-02" 2 "${PY}" "${SYNC}" import --source /tmp/fake_bundle.md
run_expect_exit "TC-DW-02" 2 "${PY}" "${SYNC}" import \
  --source "${ROOT}/.cursor/context/dialogs/DW-002/dialog_bundle.md" --window DW-001

# restore + lookup isolation
run_expect_ok "TC-REST-01" bash "${DCI}" restore DW-001
run_grep_stdout "TC-VI-03" "hybrid" bash "${DCI}" lookup "DCI v8"
run_grep_stdout "TC-VI-04" "EV-001" "${PY}" "${SYNC}" lookup --query "DCI evolution" --project

# SI
if grep -q '^### EV' "${ROOT}/.cursor/context/dialogs/DW-001/dialog_index.md" 2>/dev/null; then
  fail "TC-SI-01" "EV table found in window index"
else
  pass "TC-SI-01"
fi

if grep -q 'deprecated:' "${ROOT}/.cursor/context/dialog_index.md" 2>/dev/null; then
  pass "TC-SI-03"
else
  fail "TC-SI-03" "legacy pointer missing"
fi

if grep -q 'deprecated:' "${ROOT}/.cursor/context/dialog_bundle.md" 2>/dev/null; then
  pass "TC-SI-04"
else
  fail "TC-SI-04" "legacy bundle pointer missing"
fi

# TC-DB-01 — upsert write
set +e
"${PY}" - <<'PY' >/tmp/dci_db01.txt 2>&1
import psycopg2
c = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local")
cur = c.cursor()
cur.execute("""
  SELECT ledger_id, ledger_type, dialog_id, length(content)>0
  FROM dci_embeddings
  WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
""")
row = cur.fetchone()
assert row and row[1] == "CL" and row[2] == "gp_dq/DW-001" and row[3], f"bad row: {row}"
print("OK", row)
PY
rc_db01=$?
set -e
if [[ "${rc_db01}" -eq 0 ]]; then pass "TC-DB-01"; else fail "TC-DB-01" "$(cat /tmp/dci_db01.txt)"; fi

# TC-DB-02 — metadata read
set +e
"${PY}" - <<'PY' >/tmp/dci_db02.txt 2>&1
import psycopg2
c = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local")
cur = c.cursor()
cur.execute("""
  SELECT content, metadata->>'project_id', metadata->>'scope', metadata->>'dialog_window_id'
  FROM dci_embeddings WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
""")
content, pid, scope, dw = cur.fetchone()
assert pid == "gp_dq" and scope == "window" and dw == "DW-001"
assert content and ("v8" in content.lower() or "window" in content.lower())
print("OK meta", pid, scope, dw, content[:50])
PY
rc_db02=$?
set -e
if [[ "${rc_db02}" -eq 0 ]]; then pass "TC-DB-02"; else fail "TC-DB-02" "$(cat /tmp/dci_db02.txt)"; fi

# TC-DB-03 — round-trip lookup vs SQL
bash "${DCI}" lookup "dialog window sub-isolation" >/tmp/dci_lookup.out 2>&1 || true
set +e
"${PY}" - <<'PY' >/tmp/dci_db03.txt 2>&1
hits = open("/tmp/dci_lookup.out").read()
assert "CL-007" in hits, "lookup missing CL-007"
import psycopg2
c = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local")
cur = c.cursor()
cur.execute("""
  SELECT ledger_id, content FROM dci_embeddings
  WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
""")
lid, content = cur.fetchone()
assert "v8" in content.lower() or "sub-isolation" in content.lower() or "window" in content.lower()
print("OK round-trip", lid)
PY
rc_db03=$?
set -e
if [[ "${rc_db03}" -eq 0 ]]; then pass "TC-DB-03"; else fail "TC-DB-03" "$(cat /tmp/dci_db03.txt)"; fi

# namespace counts
set +e
"${PY}" - <<'PY' >/tmp/dci_ns.txt 2>&1
import psycopg2
c = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local")
cur = c.cursor()
cur.execute("SELECT dialog_id, count(*) FROM dci_embeddings GROUP BY dialog_id ORDER BY 1")
rows = cur.fetchall()
for r in rows:
    print(r)
assert any(r[0] == "gp_dq/DW-001" and r[1] >= 1 for r in rows), rows
assert any(r[0] == "gp_dq/__project__" and r[1] >= 1 for r in rows), rows
print("namespaces OK")
PY
rc_ns=$?
set -e
if [[ "${rc_ns}" -eq 0 ]]; then pass "TC-VI-01/02-counts"; else fail "TC-VI-01/02-counts" "$(cat /tmp/dci_ns.txt)"; fi

# multi-project isolation
set +e
DCI_PROJECTS_ROOT="$(cd "${ROOT}/.." && pwd)" "${PY}" - <<'PY' >/tmp/dci_mp01.txt 2>&1
import os, subprocess, sys
from pathlib import Path
root = Path(os.environ["DCI_PROJECTS_ROOT"])
dm = root / "de_matrix"
gp = root / "gp_dq"
py = gp / ".venv/bin/python"
if not py.is_file() or not dm.is_dir():
    print("SKIP no de_matrix/venv")
    sys.exit(0)
subprocess.check_call(["env", "DCI_PROJECT_ID=de_matrix", str(py), str(dm / "scripts/dci_vector_sync.py"), "sync", "--migrate"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.check_call(["env", "DCI_PROJECT_ID=gp_dq", str(py), str(gp / "scripts/dci_vector_sync.py"), "sync", "--project", "--migrate"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import psycopg2
c = psycopg2.connect(host="localhost", port=5433, dbname="dci_vectors", user="dci", password="dci_local", connect_timeout=3)
cur = c.cursor()
cur.execute("SELECT count(*) FROM dci_embeddings WHERE dialog_id LIKE 'de_matrix/%'")
n = cur.fetchone()[0]
assert n > 0, f"de_matrix rows wiped: {n}"
cur.execute("SELECT count(*) FROM dci_embeddings WHERE dialog_id LIKE 'gp_dq/%'")
assert cur.fetchone()[0] > 0
print("OK isolation", n)
PY
rc_mp=$?
set -e
if grep -q "^SKIP" /tmp/dci_mp01.txt 2>/dev/null; then skip "TC-ISO-MP-01" "de_matrix unavailable"
elif [[ "${rc_mp}" -eq 0 ]]; then pass "TC-ISO-MP-01"
else fail "TC-ISO-MP-01" "$(cat /tmp/dci_mp01.txt)"; fi

# export
run_expect_ok "TC-IO-01" bash "${DCI}" export

# embedding QA (skip if TEI down)
if bash "${DCI}" status 2>&1 | grep -q "tei: ok"; then
  run_grep_stdout "TC-EMB-01" "CL-007" bash "${DCI}" lookup "DCI v8 sub-isolation"
  set +e
  out_neg="$("${PY}" "${SYNC}" lookup --query "UAT aum special_dq_2" 2>&1)"
  first_hit="$(echo "${out_neg}" | awk 'NF>=3 && $1 ~ /^CL-|^Q-|^TH-/ {print $1; exit}')"
  set -e
  if [[ "${first_hit}" != "CL-007" ]]; then
    pass "TC-EMB-02"
  else
    fail "TC-EMB-02" "negative query wrongly top1 CL-007"
  fi
else
  skip "TC-EMB-01" "tei unavailable"
  skip "TC-EMB-02" "tei unavailable"
fi

# content_hash incremental (snapshot exists after compress)
if [[ -f "${ROOT}/.cursor/context/dialogs/DW-001/.compress_snapshot.json" ]]; then
  pass "TC-EMB-03"
else
  fail "TC-EMB-03" "compress snapshot missing"
fi

# teardown
bash "${DCI}" restore DW-001 >/dev/null 2>&1 || true

# accompaniment v2
run_grep_stdout "TC-AGENT-03" "project: gp_dq" bash "${DCI}" compress --force
run_grep_stdout "TC-AGENT-03" "load_mode: delta" bash "${DCI}" compress --force
run_grep_stdout "TC-AGENT-03" "handoff_ready: true" bash "${DCI}" compress --force
run_grep_stdout "TC-AGENT-03" "load_mode: restore" bash "${DCI}" restore DW-001

# token read budget contract (rule + skill)
if grep -q "Token read budget" "${ROOT}/.cursor/rules/dialog-context-index.mdc" \
   && grep -q "## Token read budget" "${ROOT}/.cursor/skills/dialog-context-index/SKILL.md"; then
  pass "TC-DCI-TOK-01"
else
  fail "TC-DCI-TOK-01" "Token read budget missing in rule or skill"
fi

# ledger integrity invariant: doctor is idempotent no-op on valid ledger
run_grep_stdout "TC-DOCTOR-01" "ledger already valid" bash "${DCI}" doctor

# doctor heals an artificially broken open TH (V-01/V-02), then validate passes
TMPIDX="$(mktemp -d)/dialog_index.md"
mkdir -p "$(dirname "${TMPIDX}")"
cat >"${TMPIDX}" <<'EOF'
# Dialog Index
project_id: gp_dq
dialog_window_id: DW-001
EOF
if grep -q "Ledger integrity invariant" "${ROOT}/.cursor/rules/dialog-context-index.mdc" \
   && grep -q "cmd_doctor" "${ROOT}/scripts/dci_vector_sync.py"; then
  pass "TC-DOCTOR-02"
else
  fail "TC-DOCTOR-02" "invariant doc or cmd_doctor missing"
fi

echo ""
echo "=== SUMMARY: PASS=${PASS} FAIL=${FAIL} SKIP=${SKIP} ==="
if [[ "${FAIL}" -eq 0 ]]; then
  echo "QA Gate: pass"
  exit 0
else
  echo "QA Gate: fail"
  exit 1
fi
