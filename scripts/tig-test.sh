#!/usr/bin/env bash
# TIG CLI + rules integration smoke tests
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PASS=0
FAIL=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1 — $2"; FAIL=$((FAIL + 1)); }

SNAP="${ROOT}/tig_snapshot.md"
DELTA="${ROOT}/tig_delta.md"
TIG_SH="${ROOT}/scripts/tig-context.sh"

echo "=== TIG test run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# TC-TIG-01: tig-context.sh runs without GUI
if [[ ! -x "${TIG_SH}" ]]; then
  fail "TC-TIG-01" "scripts/tig-context.sh missing or not executable"
else
  rc=0
  bash "${TIG_SH}" "." "origin/main" >/tmp/tig_tc01.out 2>&1 || rc=$?
  if [[ "${rc}" -eq 0 ]] && [[ -f "${SNAP}" ]] && [[ -f "${DELTA}" ]]; then
    pass "TC-TIG-01"
  else
    fail "TC-TIG-01" "exit=${rc} out=$(head -3 /tmp/tig_tc01.out | tr '\n' ' ')"
  fi
fi

# TC-TIG-02: snapshot artifact (compressed layout)
if [[ -f "${SNAP}" ]] && grep -q '"fingerprint"' "${SNAP}" \
   && grep -q "## Module map" "${SNAP}" \
   && grep -q "## Directory tree" "${SNAP}"; then
  pass "TC-TIG-02"
else
  fail "TC-TIG-02" "tig_snapshot.md missing or invalid layout"
fi

# TC-TIG-03: delta artifact with git diff sections
if [[ -f "${DELTA}" ]] && grep -q "## Unified diff vs base ref" "${DELTA}" \
   && grep -q "## Working tree diff" "${DELTA}"; then
  pass "TC-TIG-03"
else
  fail "TC-TIG-03" "tig_delta.md missing git diff sections"
fi

# TC-TIG-04: reuse-if-unchanged
out="$(bash "${TIG_SH}" "." "origin/main" 2>&1)"
if echo "${out}" | grep -q "reused"; then
  pass "TC-TIG-04"
else
  fail "TC-TIG-04" "second run did not reuse snapshot: ${out}"
fi

# TC-TIG-05: CLI without GUI
if python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('tig', '${ROOT}/tig_app_ru.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rc = mod.run_cli(['--target', '.', '--out', '/tmp/tig_test_snap2.md', '--compact', '--delta'])
assert rc == 0
" 2>/dev/null; then
  pass "TC-TIG-05"
else
  fail "TC-TIG-05" "run_cli import/execute failed"
fi

# TC-TIG-06: rules contract
if grep -q 'scripts/tig-context.sh' "${ROOT}/.cursor/rules/tig-preflight-enforced.mdc" \
   && grep -q 'tig_delta.md' "${ROOT}/.cursor/rules/tig-snapshot.mdc" \
   && grep -q 'Module map' "${ROOT}/.cursor/rules/tig-snapshot.mdc"; then
  pass "TC-TIG-06"
else
  fail "TC-TIG-06" "rules missing read-order contract"
fi

# TC-TIG-07: unified diff present (init commit show or diff)
if grep -q '```diff' "${DELTA}" && grep -qE '^(\+|diff |# base:)' "${DELTA}"; then
  pass "TC-TIG-07"
else
  fail "TC-TIG-07" "delta missing unified diff content"
fi

# TC-TIG-08: snapshot line budget ≤800
snap_lines="$(wc -l < "${SNAP}" | tr -d ' ')"
if [[ "${snap_lines}" -le 800 ]]; then
  pass "TC-TIG-08"
else
  fail "TC-TIG-08" "snapshot too large: ${snap_lines} lines (max 800)"
fi

# TC-TIG-09: delta-only postflight
before_fp="$(python3 -c "import json,re; t=open('${SNAP}').read(); print(json.loads(re.search(r'---\n(\{.*?\})\n---',t,re.S).group(1))['fingerprint'])")"
out_do="$(bash "${TIG_SH}" "." "origin/main" --delta-only 2>&1)"
after_fp="$(python3 -c "import json,re; t=open('${SNAP}').read(); print(json.loads(re.search(r'---\n(\{.*?\})\n---',t,re.S).group(1))['fingerprint'])")"
if echo "${out_do}" | grep -q "delta-only" && [[ "${before_fp}" == "${after_fp}" ]]; then
  pass "TC-TIG-09"
else
  fail "TC-TIG-09" "delta-only changed snapshot or wrong output: ${out_do}"
fi

# TC-TIG-10: base-ref fallback without origin/main
if bash "${TIG_SH}" "." "origin/main" 2>&1 | grep -qE 'fallback:(main|HEAD)'; then
  pass "TC-TIG-10"
else
  if grep -q 'base_ref_note' "${DELTA}"; then
    pass "TC-TIG-10"
  else
    fail "TC-TIG-10" "no base_ref fallback metadata"
  fi
fi

# TC-TIG-11: cross-rule TIG reuse in team-command-router + DCI separation
if grep -q 'TIG extension' "${ROOT}/.cursor/rules/team-command-router.mdc" \
   && grep -q 'tig-preflight-enforced.mdc' "${ROOT}/.cursor/rules/team-command-router.mdc" \
   && grep -q 'TIG vs DCI' "${ROOT}/.cursor/rules/dialog-context-index.mdc"; then
  pass "TC-TIG-11"
else
  fail "TC-TIG-11" "team-command-router or dialog-context-index missing TIG cross-ref"
fi

echo ""
echo "=== SUMMARY: PASS=${PASS} FAIL=${FAIL} ==="
if [[ "${FAIL}" -eq 0 ]]; then
  echo "QA Gate: pass"
  exit 0
fi
echo "QA Gate: fail"
exit 1
