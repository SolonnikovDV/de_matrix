#!/usr/bin/env bash
# Validate unified Cursor rules/skills across all projects (source = gp_dq).
set -uo pipefail

SOURCE="${RULES_VALIDATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"
REG="${SOURCE}/.cursor/dci/projects.registry"
GLOBAL_ROUTER="${HOME}/.cursor/rules/team-command-router.mdc"

PASS=0
FAIL=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1 — $2"; FAIL=$((FAIL + 1)); }

sha_file() {
  shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
}

REQUIRED_RULES=(
  dialog-context-index.mdc
  dci-working-dir-guard.mdc
  tig-preflight-enforced.mdc
  tig-snapshot.mdc
)
REQUIRED_SKILLS=(
  dialog-context-index
  tig-snapshot
)
REQUIRED_SCRIPTS=(
  scripts/dci-vector.sh
  scripts/tig-context.sh
)

check_same_sha() {
  local id="$1" src="$2" dst="$3"
  if [[ ! -f "${dst}" ]]; then
    fail "${id}" "missing ${dst}"
    return
  fi
  local s1 s2
  s1="$(sha_file "${src}")"
  s2="$(sha_file "${dst}")"
  if [[ "${s1}" == "${s2}" ]]; then
    pass "${id}"
  else
    fail "${id}" "sha mismatch (run dci-propagate.sh)"
  fi
}

check_rule_contract() {
  local pid="$1" path="$2"
  local dci="${path}/.cursor/rules/dialog-context-index.mdc"
  if grep -q "Token read budget" "${dci}" && grep -q "TIG vs DCI" "${dci}"; then
    pass "${pid}-dci-token-contract"
  else
    fail "${pid}-dci-token-contract" "dialog-context-index missing Token read budget or TIG vs DCI"
  fi
  local skill="${path}/.cursor/skills/dialog-context-index/SKILL.md"
  if grep -q "## Token read budget" "${skill}" && grep -q "## Latency" "${skill}"; then
    pass "${pid}-dci-skill-contract"
  else
    fail "${pid}-dci-skill-contract" "DCI skill missing Token read budget or Latency"
  fi
  if grep -q "Working directory resolution" "${dci}" && grep -q "materialize" "${dci}"; then
    pass "${pid}-dci-workdir-contract"
  else
    fail "${pid}-dci-workdir-contract" "dialog-context-index missing Working dir / materialize-compress contract"
  fi
  local guard="${path}/.cursor/rules/dci-working-dir-guard.mdc"
  if [[ -f "${guard}" ]] && grep -q "DCI not deployed" "${guard}"; then
    pass "${pid}-dci-guard-present"
  else
    fail "${pid}-dci-guard-present" "dci-working-dir-guard.mdc missing or invalid"
  fi
}

check_custom_rule_contract() {
  local pid="$1" path="$2"
  local dci="${path}/.cursor/rules/dialog-context-index.mdc"
  local guard="${path}/.cursor/rules/dci-working-dir-guard.mdc"
  local router="${path}/.cursor/rules/team-command-router.mdc"

  # Legacy triggers must be fully removed from authoritative rules.
  if grep -nE "(контекст:|команда:|эволюция:|/team )" "${dci}" "${guard}" "${router}" >/dev/null 2>&1; then
    fail "${pid}-legacy-trigger-ban" "legacy triggers found in DCI/guard/router"
  else
    pass "${pid}-legacy-trigger-ban"
  fi

  # Mandatory keys for deterministic routing.
  local required=(
    "/custom-rule: dci compress"
    "/custom-rule: dci materialize"
    "/custom-rule: dci windows"
    "/custom-rule: dci projects"
    "/custom-rule: dci restore DW-NNN"
    "/custom-rule: team sql"
    "/custom-rule: team b2c"
    "/custom-rule: team de-matrix"
    "/custom-rule: team web-app"
    "/custom-rule: team presentation"
    "/custom-rule: team auto"
    "/custom-rule: team reset"
    "/custom-rule: evo report"
    "/custom-rule: evo diff"
    "/custom-rule: evo branch-status"
    "/custom-rule: evo regress"
  )
  local missing=()
  for k in "${required[@]}"; do
    if ! grep -nF "${k}" "${dci}" "${guard}" "${router}" >/dev/null 2>&1; then
      missing+=("${k}")
    fi
  done
  if [[ "${#missing[@]}" -eq 0 ]]; then
    pass "${pid}-custom-rule-required-keys"
  else
    fail "${pid}-custom-rule-required-keys" "missing keys: ${missing[*]}"
  fi

  # Reserved slash commands must not be hijacked by rule keys.
  if grep -nE "/custom-rule:[[:space:]]*(plan|agent|ask|debug|mode|memory)\\b" "${dci}" "${guard}" "${router}" >/dev/null 2>&1; then
    fail "${pid}-custom-rule-reserved-conflict" "reserved slash-key conflict detected"
  else
    pass "${pid}-custom-rule-reserved-conflict"
  fi

  # Authoritative DCI map should have unique one-key-one-action rows.
  local map_rows map_actions uniq_actions
  map_rows="$(
    awk '
      /Token map/ {in_map=1; next}
      /Single source of truth/ {in_map=0}
      in_map && $0 ~ /^\| `[^`]+` \|/ {print}
    ' "${guard}" | wc -l | tr -d ' '
  )"
  map_actions="$(
    awk -F'\\|' '
      /Token map/ {in_map=1; next}
      /Single source of truth/ {in_map=0}
      in_map && $0 ~ /^\| `[^`]+` \|/ {
        a=$3; gsub(/^[[:space:]]+|[[:space:]]+$/,"",a); print a
      }
    ' "${guard}" | wc -l | tr -d ' '
  )"
  uniq_actions="$(
    awk -F'\\|' '
      /Token map/ {in_map=1; next}
      /Single source of truth/ {in_map=0}
      in_map && $0 ~ /^\| `[^`]+` \|/ {
        a=$3; gsub(/^[[:space:]]+|[[:space:]]+$/,"",a); print a
      }
    ' "${guard}" | sort -u | wc -l | tr -d ' '
  )"
  if [[ "${map_rows}" -eq 8 ]] && [[ "${map_actions}" -eq "${uniq_actions}" ]]; then
    pass "${pid}-custom-rule-unique-map"
  else
    fail "${pid}-custom-rule-unique-map" "guard token map invalid (rows=${map_rows}, unique_actions=${uniq_actions})"
  fi
}

check_router() {
  local pid="$1" path="$2"
  local local_router="${path}/.cursor/rules/team-command-router.mdc"
  local src_router="${SOURCE}/.cursor/rules/team-command-router.mdc"
  if [[ -f "${local_router}" ]] && grep -q "Team Router Inheritance" "${local_router}"; then
    if grep -q "TIG (project-local)" "${local_router}" && grep -q "DCI (project-local)" "${local_router}"; then
      pass "${pid}-router-inheritance-stub"
    else
      fail "${pid}-router-inheritance-stub" "stub missing DCI/TIG sections"
    fi
    check_same_sha "${pid}-router-global" "${src_router}" "${GLOBAL_ROUTER}"
  elif [[ -f "${local_router}" ]]; then
    check_same_sha "${pid}-router-full" "${src_router}" "${local_router}"
  else
    fail "${pid}-router" "team-command-router.mdc missing"
  fi
}

echo "=== Rules validate all projects $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "source: ${SOURCE}"

for rule in "${REQUIRED_RULES[@]}"; do
  [[ -f "${SOURCE}/.cursor/rules/${rule}" ]] || fail "source-${rule}" "missing in source"
done

# global guard fires on контекст:* even in worktrees without project rules
check_same_sha "global-dci-guard" \
  "${SOURCE}/.cursor/rules/dci-working-dir-guard.mdc" \
  "${HOME}/.cursor/rules/dci-working-dir-guard.mdc"

while IFS= read -r line; do
  [[ "${line}" =~ ^# ]] && continue
  [[ -z "${line}" ]] && continue
  pid="${line%%|*}"
  path="${line#*|}"
  [[ -d "${path}/.cursor" ]] || continue

  echo "--- ${pid} ---"
  for rule in "${REQUIRED_RULES[@]}"; do
    check_same_sha "${pid}-${rule}" \
      "${SOURCE}/.cursor/rules/${rule}" \
      "${path}/.cursor/rules/${rule}"
  done
  for skill in "${REQUIRED_SKILLS[@]}"; do
    check_same_sha "${pid}-skill-${skill}" \
      "${SOURCE}/.cursor/skills/${skill}/SKILL.md" \
      "${path}/.cursor/skills/${skill}/SKILL.md"
  done
  for script in "${REQUIRED_SCRIPTS[@]}"; do
    check_same_sha "${pid}-${script//\//-}" \
      "${SOURCE}/${script}" \
      "${path}/${script}"
  done
  check_rule_contract "${pid}" "${path}"
  check_custom_rule_contract "${pid}" "${path}"
  check_router "${pid}" "${path}"
done < "${REG}"

echo ""
echo "=== SUMMARY: PASS=${PASS} FAIL=${FAIL} ==="
[[ "${FAIL}" -eq 0 ]]
