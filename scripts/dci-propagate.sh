#!/usr/bin/env bash
# Propagate DCI v9 rule + scripts + infra from gp_dq to other Cursor projects.
set -euo pipefail

SOURCE="${DCI_PROPAGATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"
DRY="${DCI_PROPAGATE_DRY:-0}"

copy_file() {
  local src="$1" dst="$2"
  if [[ ! -f "${src}" ]]; then
    echo "WARN missing source: ${src}" >&2
    return 0
  fi
  mkdir -p "$(dirname "${dst}")"
  if [[ "${DRY}" == "1" ]]; then
    echo "DRY copy ${src} -> ${dst}"
  else
    cp -f "${src}" "${dst}"
  fi
}

bootstrap_project() {
  local target="$1"
  local pid="$2"
  local catalog="${target}/.cursor/context/project_catalog.md"
  if [[ -f "${catalog}" ]]; then
    echo "  bootstrap: skip (project_catalog exists)"
    return 0
  fi
  echo "  bootstrap: project_catalog + DW-001 for ${pid}"
  local now
  now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  mkdir -p "${target}/.cursor/context/dialogs/DW-001"
  cat >"${catalog}" <<EOF
# Project Catalog

project_id: ${pid}
master_branch: EV-PROJECT
active_window: DW-001
refreshed: ${now}

## branch_registry

| id | state | parent | summary | delta | links |
|----|-------|--------|---------|-------|-------|
| EV-PROJECT | master | — | ${pid} project root namespace | root namespace | — |

## checkpoint_registry

| id | label | ev | status | evidence |
|----|-------|-----|--------|----------|
| — | none | — | — | — |

## window_registry

| id | slot | lifecycle | name | description | updated | path | linked_branches |
|----|------|-----------|------|-------------|---------|------|-----------------|
| DW-001 | active | open | Initial dialog window | Primary dialog window for ${pid} | ${now:0:10} | .cursor/context/dialogs/DW-001/ | [] |

## lookup_index

### by_window
- DW-001: Initial dialog window

### by_branch
- EV-PROJECT: master

### by_keyword
- dci: [DW-001]
EOF

  cat >"${target}/.cursor/context/dialogs/DW-001/dialog_index.md" <<EOF
# Dialog Index

project_id: ${pid}
dialog_window_id: DW-001
window_name: Initial dialog window
window_description: Primary dialog window for ${pid}
master_branch: EV-PROJECT
linked_branches: []
session: initial | team: none | refreshed: ${now}

## ledger_map

### Q
| id | text | status | links |
|----|------|--------|-------|
| Q-001 | Initial dialog window for ${pid} | open | — |

### CL
| id | scope | verdict | status | evidence | links |
|----|-------|---------|--------|----------|-------|

### TH
| id | topic | status | parent | links |
|----|-------|--------|--------|-------|
| TH-001 | Initial dialog window | open | Q-001 | — |

## thread_map

| th | status | topic | next_action |
|----|--------|-------|-------------|
| TH-001 | open | Initial dialog window | record first CL/EV on session start |

## lookup_index

### by_id
- Q-001, TH-001: open

### by_status
- open: [Q-001, TH-001]

### hot_open
- TH-001

## open_risks

| ref | risk | owner | next_action |
|-----|------|-------|-------------|
| TH-001 | fresh window, no conclusions yet | — | record CL/EV on first session |
EOF

  cat >"${target}/.cursor/context/dialogs/DW-001/dialog_delta.md" <<EOF
# Dialog Delta

since: ${now}
dialog_window_id: DW-001

## new_or_updated
- Q-001
- TH-001

## superseded
- none

## project_delta
- none

## open_risks
- none
EOF

  cat >"${target}/.cursor/context/dialog_index.md" <<EOF
# Dialog Index (pointer — DCI v9)

deprecated: use project_catalog.md and dialogs/DW-NNN/dialog_index.md
project_id: ${pid}
active_window: DW-001
see: .cursor/context/project_catalog.md
EOF

  cat >"${target}/.cursor/context/dialog_delta.md" <<EOF
# Dialog Delta (pointer — DCI v9)

deprecated: use dialogs/DW-NNN/dialog_delta.md
project_id: ${pid}
canonical_delta: .cursor/context/dialogs/DW-001/dialog_delta.md
see: .cursor/context/project_catalog.md
EOF

  cat >"${target}/.cursor/context/dialog_bundle.md" <<EOF
# Dialog Bundle (pointer — DCI v9)

deprecated: use dialogs/DW-NNN/dialog_bundle.md
archive: true
project_id: ${pid}
see: .cursor/context/project_catalog.md
EOF

  cat >"${target}/.cursor/context/.dialog_window_lock" <<EOF
dialog_window_id: DW-001
locked_at: ${now}
EOF

  cat >"${target}/.cursor/context/.project_lock" <<EOF
project_id: ${pid}
locked_at: ${now}
EOF
}

repair_bootstrap_ledger() {
  # Self-heal legacy/hand-edited windows via the propagated core `doctor`
  # (single source of truth). Idempotent; no-op when ledger already valid.
  local target="$1"
  [[ -f "${target}/scripts/dci-vector.sh" ]] || return 0
  if [[ "${DRY}" == "1" ]]; then
    echo "  repair-ledger: dry (skip)"
    return 0
  fi
  local out
  out="$(cd "${target}" && bash scripts/dci-vector.sh doctor 2>&1)" || true
  echo "${out}" | sed 's/^/  /'
}

write_env() {
  local target="$1" pid="$2"
  local envf="${target}/.cursor/dci/dci.env"
  if [[ -f "${envf}" ]]; then
    echo "  dci.env: keep existing"
    return 0
  fi
  cat >"${envf}" <<EOF
# DCI vector store (pgvector container on port 5433)
DCI_VECTOR_HOST=localhost
DCI_VECTOR_PORT=5433
DCI_VECTOR_DB=dci_vectors
DCI_VECTOR_USER=dci
DCI_VECTOR_PASSWORD=dci_local
DCI_PROJECT_ID=${pid}

# Local embed server — enabled by dci-setup-projects.sh / dci-vector.sh up
# DCI_EMBED_URL=http://localhost:18081/embed
# DCI_EMBED_MODEL=intfloat/multilingual-e5-small
EOF
}

update_inheritance_router() {
  local target="$1"
  local router="${target}/.cursor/rules/team-command-router.mdc"
  [[ -f "${router}" ]] || return 0
  if ! grep -q "Team Router Inheritance" "${router}" 2>/dev/null; then
    return 0
  fi
  cat >"${router}" <<'EOF'
---
description: Inherit global team command router defaults
alwaysApply: true
---

# Team Router Inheritance

Use `~/.cursor/rules/team-command-router.mdc` as the authoritative router for this project.

Apply all command workflows from the global router, including:
- `/custom-rule: team sql`
- `/custom-rule: team b2c`
- `/custom-rule: team de-matrix`
- `/custom-rule: team web-app`
- `/custom-rule: team presentation`
- `/custom-rule: team auto`

## DCI (project-local)

Follow `.cursor/rules/dialog-context-index.mdc` and `.cursor/skills/dialog-context-index/SKILL.md`.
Shell: `bash scripts/dci-vector.sh` (compress, materialize, doctor, windows, restore, projects, validate).

## TIG (project-local)

Follow `.cursor/rules/tig-preflight-enforced.mdc` and `.cursor/rules/tig-snapshot.mdc`.
Shell: `bash scripts/tig-context.sh` (preflight / `--delta-only` postflight).
EOF
  echo "  team-command-router: inheritance stub refreshed (DCI + TIG)"
}

propagate_rules_and_tig() {
  local target="$1"
  local rules=(
    dialog-context-index.mdc
    dci-working-dir-guard.mdc
    tig-preflight-enforced.mdc
    tig-snapshot.mdc
    presentation-team-methodology.mdc
  )
  for r in "${rules[@]}"; do
    copy_file "${SOURCE}/.cursor/rules/${r}" "${target}/.cursor/rules/${r}"
  done
  local skills=(
    dialog-context-index
    tig-snapshot
    sql-team
    b2c-team
    de-matrix-team
    web-app-team
    presentation-team
  )
  for s in "${skills[@]}"; do
    copy_file "${SOURCE}/.cursor/skills/${s}/SKILL.md" "${target}/.cursor/skills/${s}/SKILL.md"
  done
  copy_file "${SOURCE}/tig_app_ru.py" "${target}/tig_app_ru.py"
  copy_file "${SOURCE}/scripts/tig-context.sh" "${target}/scripts/tig-context.sh"
  copy_file "${SOURCE}/scripts/tig-test.sh" "${target}/scripts/tig-test.sh"
  copy_file "${SOURCE}/scripts/rules-validate-all-projects.sh" "${target}/scripts/rules-validate-all-projects.sh"
  chmod +x "${target}/scripts/tig-context.sh" "${target}/scripts/tig-test.sh" "${target}/scripts/rules-validate-all-projects.sh" 2>/dev/null || true
}

sync_global_router() {
  local global="${HOME}/.cursor/rules/team-command-router.mdc"
  mkdir -p "$(dirname "${global}")"
  if [[ "${DRY}" == "1" ]]; then
    echo "DRY copy ${SOURCE}/.cursor/rules/team-command-router.mdc -> ${global}"
  else
    cp -f "${SOURCE}/.cursor/rules/team-command-router.mdc" "${global}"
    echo "Updated global router: ${global}"
  fi
}

sync_global_dci_guard() {
  # Global working-dir guard fires on контекст:* even in worktrees lacking the
  # project DCI rule — prevents improvisation when DCI is not deployed.
  local src="${SOURCE}/.cursor/rules/dci-working-dir-guard.mdc"
  local global="${HOME}/.cursor/rules/dci-working-dir-guard.mdc"
  [[ -f "${src}" ]] || src="${global}"
  [[ -f "${src}" ]] || { echo "WARN: no dci-working-dir-guard.mdc source"; return 0; }
  mkdir -p "$(dirname "${global}")"
  if [[ "${DRY}" == "1" ]]; then
    echo "DRY copy ${src} -> ${global}"
  else
    cp -f "${src}" "${global}"
    echo "Updated global DCI guard: ${global}"
  fi
}

propagate_one() {
  local target="$1"
  local name
  name="$(basename "${target}")"
  if [[ "${target}" == "${SOURCE}" ]]; then
    echo "SKIP source ${name}"
    return 0
  fi
  if [[ ! -d "${target}/.cursor" ]]; then
    echo "SKIP ${name} (no .cursor/)"
    return 0
  fi

  echo "=== ${name} ==="
  propagate_rules_and_tig "${target}"
  copy_file "${SOURCE}/.cursor/context/dci_test_cases.md" "${target}/.cursor/context/dci_test_cases.md"
  copy_file "${SOURCE}/scripts/dci_vector_sync.py" "${target}/scripts/dci_vector_sync.py"
  copy_file "${SOURCE}/scripts/dci-vector.sh" "${target}/scripts/dci-vector.sh"
  copy_file "${SOURCE}/scripts/dci-test.sh" "${target}/scripts/dci-test.sh"
  copy_file "${SOURCE}/scripts/dci-propagate.sh" "${target}/scripts/dci-propagate.sh"
  copy_file "${SOURCE}/scripts/dci-setup-projects.sh" "${target}/scripts/dci-setup-projects.sh"
  copy_file "${SOURCE}/.cursor/dci/docker-compose.yml" "${target}/.cursor/dci/docker-compose.yml"
  copy_file "${SOURCE}/.cursor/dci/dci.env.example" "${target}/.cursor/dci/dci.env.example"
  copy_file "${SOURCE}/scripts/dci_embed_server.py" "${target}/scripts/dci_embed_server.py"
  copy_file "${SOURCE}/.cursor/dci/embedding_golden.json" "${target}/.cursor/dci/embedding_golden.json"
  copy_file "${SOURCE}/.cursor/dci/init/01_schema.sql" "${target}/.cursor/dci/init/01_schema.sql"
  copy_file "${SOURCE}/.cursor/dci/init/02_window_scope.sql" "${target}/.cursor/dci/init/02_window_scope.sql"
  copy_file "${SOURCE}/.cursor/dci/projects.registry" "${target}/.cursor/dci/projects.registry"
  copy_file "${SOURCE}/scripts/dci-validate-all-projects.sh" "${target}/scripts/dci-validate-all-projects.sh"
  chmod +x "${target}/scripts/dci-vector.sh" "${target}/scripts/dci-test.sh" "${target}/scripts/dci-propagate.sh" "${target}/scripts/dci-setup-projects.sh" "${target}/scripts/dci-validate-all-projects.sh" 2>/dev/null || true

  bootstrap_project "${target}" "${name}"
  repair_bootstrap_ledger "${target}"
  write_env "${target}" "${name}"

  if [[ -f "${target}/.cursor/rules/team-command-router.mdc" ]] && grep -q "Team Router Inheritance" "${target}/.cursor/rules/team-command-router.mdc" 2>/dev/null; then
    update_inheritance_router "${target}"
  elif [[ -f "${SOURCE}/.cursor/rules/team-command-router.mdc" ]]; then
    copy_file "${SOURCE}/.cursor/rules/team-command-router.mdc" "${target}/.cursor/rules/team-command-router.mdc"
    echo "  team-command-router: synced from source"
  fi
}

write_projects_registry() {
  local reg="${SOURCE}/.cursor/dci/projects.registry"
  local tmp
  tmp="$(mktemp)"
  {
    echo "# project_id|absolute_path"
    for dir in "${ROOT}"/*; do
      [[ -d "${dir}/.cursor" ]] || continue
      echo "$(basename "${dir}")|${dir}"
    done
  } >"${tmp}"
  if [[ "${DRY}" == "1" ]]; then
    cat "${tmp}"
    rm -f "${tmp}"
  else
    mv "${tmp}" "${reg}"
    echo "Updated ${reg}"
  fi
}

chmod +x "${SOURCE}/scripts/dci-propagate.sh" "${SOURCE}/scripts/dci-vector.sh" "${SOURCE}/scripts/dci-test.sh" 2>/dev/null || true

for dir in "${ROOT}"/*; do
  [[ -d "${dir}" ]] || continue
  propagate_one "${dir}"
done

write_projects_registry
sync_global_router
sync_global_dci_guard
echo "Done."
