---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-14T14:22:15Z",
  "base_ref": "origin/main",
  "base_ref_note": "origin/main",
  "snapshot": "/Users/dmitrysolonnikov/PycharmProjects/de_matrix/.cursor/context/tig/tig_snapshot.md",
  "snapshot_reused": true,
  "fingerprint": "sha256:9b2512005568ebce",
  "git_head": "52e09d36f569f5d9bac946b073fc6e91edd54cf9",
  "git_dirty": true
}
---

# TIG Delta Report

- **Snapshot:** `tig_snapshot.md` (reused)
- **Fingerprint:** `sha256:9b2512005568ebce`
- **Base ref:** `origin/main` (origin/main)

## Working tree

```text
M .gitignore
 D README_CUSTOM_RULES.md
 D scripts/dci-propagate.sh
 D scripts/dci-setup-projects.sh
 D scripts/dci-test.sh
 D scripts/dci-validate-all-projects.sh
 D scripts/dci-vector.sh
 D scripts/dci_embed_server.py
 D scripts/dci_vector_sync.py
 D scripts/rules-validate-all-projects.sh
 D scripts/tig-context.sh
 D scripts/tig-test.sh
 D tig_delta.md
 D tig_snapshot.md
?? .cursor/
```

## Commits since base ref

```text
(no commits)
```

## Changed files vs base ref

```text
(no diff vs base ref)
```

## Unified diff vs base ref

```diff
# base: origin/main (origin/main)
(no committed diff vs base ref)
```

## Working tree diff

```diff
## Unstaged
diff --git a/.gitignore b/.gitignore
index 8ea5be8..7b08430 100644
--- a/.gitignore
+++ b/.gitignore
@@ -3,7 +3,6 @@
 # ----------------------------
 .idea/
 .vscode/
-.cursor/
 .gigaide/
 .venv/
 .pytest_cache/
@@ -60,12 +59,15 @@ proxy/certs/provided/*
 
 # --- DCI local/runtime (do not publish) ---
 .cursor/dci/dci.env
+.cursor/dci/.embed_server.pid
+.cursor/dci/embed_server.log
 .cursor/context/.project_lock
 .cursor/context/.dialog_window_lock
 .cursor/context/vector_fallback.jsonl
+.cursor/context/dialogs/**/vector_fallback.jsonl
+.cursor/context/vector_index.meta.md
+.cursor/context/dialogs/**/vector_index.meta.md
 .cursor/context/.compress_snapshot.project.json
 .cursor/context/dialogs/**/.compress_snapshot.json
-.cursor/context/dialogs/**/dialog_bundle.md
 .cursor/context/dialog_bundle.md
-.cursor/context/vector_index.meta.md
-.cursor/context/dialogs/**/vector_index.meta.md
+.cursor/context/dialogs/**/dialog_bundle.md
diff --git a/README_CUSTOM_RULES.md b/README_CUSTOM_RULES.md
deleted file mode 100644
index 8e16f81..0000000
--- a/README_CUSTOM_RULES.md
+++ /dev/null
@@ -1,101 +0,0 @@
-# Custom Rule Commands Runbook
-
-This document explains how to use `/custom-rule:` commands: command meaning, recommended execution order, and expected effect.
-
-## Command format
-
-All rule commands use one prefix:
-
-`/custom-rule: <namespace> <command> [args]`
-
-Namespaces:
-
-- `dci` - dialog context index operations (compress/restore/windows/projects/doctor)
-- `team` - team router selection/reset
-- `evo` - evolution ledger views
-
-## Quick start order
-
-Use this order for a normal working session:
-
-1. Check current windows/tree:
-   - `/custom-rule: dci windows`
-   - Effect: shows EV/DW structure for current repo and active window state.
-2. If needed, switch or create window:
-   - `/custom-rule: dci restore DW-001`
-   - `/custom-rule: dci restore-new "summary"`
-   - Effect: loads target dialog window context (delta-first).
-3. Select team workflow:
-   - `/custom-rule: team sql|b2c|de-matrix|web-app|presentation|auto`
-   - Effect: locks chat to selected team routing until explicit reset.
-4. Work in the session (implement/review/discuss).
-5. Before handoff, compress context:
-   - `/custom-rule: dci compress`
-   - Effect: materialize + doctor + validate + sync + delta export + restore command for next chat.
-
-## DCI commands and effects
-
-- `/custom-rule: dci windows`
-  - Shows project branch tree and dialog windows.
-- `/custom-rule: dci projects`
-  - Shows multi-project tree from registry/root.
-- `/custom-rule: dci restore DW-NNN`
-  - Restores a specific dialog window (delta mode).
-- `/custom-rule: dci restore-new "summary"`
-  - Creates and activates a new dialog window.
-- `/custom-rule: dci materialize`
-  - Builds reusable CP-* checkpoints from the active window state.
-- `/custom-rule: dci compress`
-  - Runs `materialize -> doctor -> validate -> sync/export` and prints handoff block:
-    `restore: /custom-rule: dci restore DW-NNN`.
-- `/custom-rule: dci expand CL-NNN` (or `EV-NNN`)
-  - Opens explicit ledger body by ID.
-
-## Team commands and effects
-
-- `/custom-rule: team sql`
-- `/custom-rule: team b2c`
-- `/custom-rule: team de-matrix`
-- `/custom-rule: team web-app`
-- `/custom-rule: team presentation`
-- `/custom-rule: team auto`
-- `/custom-rule: team reset`
-
-Effect:
-
-- Selects or resets active team routing logic for the current chat.
-- While team is locked, implicit auto-switching is disabled.
-
-## Evolution commands and effects
-
-- `/custom-rule: evo report`
-- `/custom-rule: evo diff <EV-id|CL-id|topic>`
-- `/custom-rule: evo branch-status`
-- `/custom-rule: evo regress <EV-id|range|topic>`
-
-Effect:
-
-- Produces evolution-oriented views using EV/CL linkage without changing DCI window state.
-
-## Recommended failure handling order
-
-If DCI command fails:
-
-1. Optionally run `/custom-rule: dci materialize` if you need explicit checkpoint build
-2. Retry `/custom-rule: dci compress`
-3. If embed backend is unavailable, run infra recovery:
-   - `bash scripts/dci-vector.sh up`
-   - then retry `/custom-rule: dci compress`
-4. Use force only with explicit risk acceptance:
-   - `bash scripts/dci-vector.sh compress --force`
-
-## Worktree note
-
-If the chat runs in a worktree (`~/.cursor/worktrees/...`) and DCI files are missing there, commands should not be improvised.
-
-Expected behavior:
-
-- report `DCI not deployed in this working copy`
-- recover by opening the main checkout under `~/PycharmProjects/<project>` or by propagating rules from source.
-
-Note: `doctor` exists as a debug-only fallback (`bash scripts/dci-vector.sh doctor`) and is normally executed internally by `compress`.
diff --git a/scripts/dci-propagate.sh b/scripts/dci-propagate.sh
deleted file mode 100755
index f261a6f..0000000
--- a/scripts/dci-propagate.sh
+++ /dev/null
@@ -1,387 +0,0 @@
-#!/usr/bin/env bash
-# Propagate DCI v9 rule + scripts + infra from gp_dq to other Cursor projects.
-set -euo pipefail
-
-SOURCE="${DCI_PROPAGATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
-ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"
-DRY="${DCI_PROPAGATE_DRY:-0}"
-
-copy_file() {
-  local src="$1" dst="$2"
-  if [[ ! -f "${src}" ]]; then
-    echo "WARN missing source: ${src}" >&2
-    return 0
-  fi
-  mkdir -p "$(dirname "${dst}")"
-  if [[ "${DRY}" == "1" ]]; then
-    echo "DRY copy ${src} -> ${dst}"
-  else
-    cp -f "${src}" "${dst}"
-  fi
-}
-
-bootstrap_project() {
-  local target="$1"
-  local pid="$2"
-  local catalog="${target}/.cursor/context/project_catalog.md"
-  if [[ -f "${catalog}" ]]; then
-    echo "  bootstrap: skip (project_catalog exists)"
-    return 0
-  fi
-  echo "  bootstrap: project_catalog + DW-001 for ${pid}"
-  local now
-  now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
-  mkdir -p "${target}/.cursor/context/dialogs/DW-001"
-  cat >"${catalog}" <<EOF
-# Project Catalog
-
-project_id: ${pid}
-master_branch: EV-PROJECT
-active_window: DW-001
-refreshed: ${now}
-
-## branch_registry
-
-| id | state | parent | summary | delta | links |
-|----|-------|--------|---------|-------|-------|
-| EV-PROJECT | master | — | ${pid} project root namespace | root namespace | — |
-
-## checkpoint_registry
-
-| id | label | ev | status | evidence |
-|----|-------|-----|--------|----------|
-| — | none | — | — | — |
-
-## window_registry
-
-| id | slot | lifecycle | name | description | updated | path | linked_branches |
-|----|------|-----------|------|-------------|---------|------|-----------------|
-| DW-001 | active | open | Initial dialog window | Primary dialog window for ${pid} | ${now:0:10} | .cursor/context/dialogs/DW-001/ | [] |
-
-## lookup_index
-
-### by_window
-- DW-001: Initial dialog window
-
-### by_branch
-- EV-PROJECT: master
-
-### by_keyword
-- dci: [DW-001]
-EOF
-
-  cat >"${target}/.cursor/context/dialogs/DW-001/dialog_index.md" <<EOF
-# Dialog Index
-
-project_id: ${pid}
-dialog_window_id: DW-001
-window_name: Initial dialog window
-window_description: Primary dialog window for ${pid}
-master_branch: EV-PROJECT
-linked_branches: []
-session: initial | team: none | refreshed: ${now}
-
-## ledger_map
-
-### Q
-| id | text | status | links |
-|----|------|--------|-------|
-| Q-001 | Initial dialog window for ${pid} | open | — |
-
-### CL
-| id | scope | verdict | status | evidence | links |
-|----|-------|---------|--------|----------|-------|
-
-### TH
-| id | topic | status | parent | links |
-|----|-------|--------|--------|-------|
-| TH-001 | Initial dialog window | open | Q-001 | — |
-
-## thread_map
-
-| th | status | topic | next_action |
-|----|--------|-------|-------------|
-| TH-001 | open | Initial dialog window | record first CL/EV on session start |
-
-## lookup_index
-
-### by_id
-- Q-001, TH-001: open
-
-### by_status
-- open: [Q-001, TH-001]
-
-### hot_open
-- TH-001
-
-## open_risks
-
-| ref | risk | owner | next_action |
-|-----|------|-------|-------------|
-| TH-001 | fresh window, no conclusions yet | — | record CL/EV on first session |
-EOF
-
-  cat >"${target}/.cursor/context/dialogs/DW-001/dialog_delta.md" <<EOF
-# Dialog Delta
-
-since: ${now}
-dialog_window_id: DW-001
-
-## new_or_updated
-- Q-001
-- TH-001
-
-## superseded
-- none
-
-## project_delta
-- none
-
-## open_risks
-- none
-EOF
-
-  cat >"${target}/.cursor/context/dialog_index.md" <<EOF
-# Dialog Index (pointer — DCI v9)
-
-deprecated: use project_catalog.md and dialogs/DW-NNN/dialog_index.md
-project_id: ${pid}
-active_window: DW-001
-see: .cursor/context/project_catalog.md
-EOF
-
-  cat >"${target}/.cursor/context/dialog_delta.md" <<EOF
-# Dialog Delta (pointer — DCI v9)
-
-deprecated: use dialogs/DW-NNN/dialog_delta.md
-project_id: ${pid}
-canonical_delta: .cursor/context/dialogs/DW-001/dialog_delta.md
-see: .cursor/context/project_catalog.md
-EOF
-
-  cat >"${target}/.cursor/context/dialog_bundle.md" <<EOF
-# Dialog Bundle (pointer — DCI v9)
-
-deprecated: use dialogs/DW-NNN/dialog_bundle.md
-archive: true
-project_id: ${pid}
-see: .cursor/context/project_catalog.md
-EOF
-
-  cat >"${target}/.cursor/context/.dialog_window_lock" <<EOF
-dialog_window_id: DW-001
-locked_at: ${now}
-EOF
-
-  cat >"${target}/.cursor/context/.project_lock" <<EOF
-project_id: ${pid}
-locked_at: ${now}
-EOF
-}
-
-repair_bootstrap_ledger() {
-  # Self-heal legacy/hand-edited windows via the propagated core `doctor`
-  # (single source of truth). Idempotent; no-op when ledger already valid.
-  local target="$1"
-  [[ -f "${target}/scripts/dci-vector.sh" ]] || return 0
-  if [[ "${DRY}" == "1" ]]; then
-    echo "  repair-ledger: dry (skip)"
-    return 0
-  fi
-  local out
-  out="$(cd "${target}" && bash scripts/dci-vector.sh doctor 2>&1)" || true
-  echo "${out}" | sed 's/^/  /'
-}
-
-write_env() {
-  local target="$1" pid="$2"
-  local envf="${target}/.cursor/dci/dci.env"
-  if [[ -f "${envf}" ]]; then
-    echo "  dci.env: keep existing"
-    return 0
-  fi
-  cat >"${envf}" <<EOF
-# DCI vector store (pgvector container on port 5433)
-DCI_VECTOR_HOST=localhost
-DCI_VECTOR_PORT=5433
-DCI_VECTOR_DB=dci_vectors
-DCI_VECTOR_USER=dci
-DCI_VECTOR_PASSWORD=dci_local
-DCI_PROJECT_ID=${pid}
-
-# Local embed server — enabled by dci-setup-projects.sh / dci-vector.sh up
-# DCI_EMBED_URL=http://localhost:18081/embed
-# DCI_EMBED_MODEL=intfloat/multilingual-e5-small
-EOF
-}
-
-update_inheritance_router() {
-  local target="$1"
-  local router="${target}/.cursor/rules/team-command-router.mdc"
-  [[ -f "${router}" ]] || return 0
-  if ! grep -q "Team Router Inheritance" "${router}" 2>/dev/null; then
-    return 0
-  fi
-  cat >"${router}" <<'EOF'
----
-description: Inherit global team command router defaults
-alwaysApply: true
----
-
-# Team Router Inheritance
-
-Use `~/.cursor/rules/team-command-router.mdc` as the authoritative router for this project.
-
-Apply all command workflows from the global router, including:
-- `/custom-rule: team sql`
-- `/custom-rule: team b2c`
-- `/custom-rule: team de-matrix`
-- `/custom-rule: team web-app`
-- `/custom-rule: team presentation`
-- `/custom-rule: team auto`
-
-## DCI (project-local)
-
-Follow `.cursor/rules/dialog-context-index.mdc` and `.cursor/skills/dialog-context-index/SKILL.md`.
-Shell: `bash scripts/dci-vector.sh` (compress, materialize, doctor, windows, restore, projects, validate).
-
-## TIG (project-local)
-
-Follow `.cursor/rules/tig-preflight-enforced.mdc` and `.cursor/rules/tig-snapshot.mdc`.
-Shell: `bash scripts/tig-context.sh` (preflight / `--delta-only` postflight).
-EOF
-  echo "  team-command-router: inheritance stub refreshed (DCI + TIG)"
-}
-
... [working tree diff: truncated, 4786 lines omitted]
```
