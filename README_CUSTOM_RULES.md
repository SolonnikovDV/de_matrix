# Custom Rule Commands Runbook

This document explains how to use `/custom-rule:` commands: command meaning, recommended execution order, and expected effect.

## Command format

All rule commands use one prefix:

`/custom-rule: <namespace> <command> [args]`

Namespaces:

- `dci` - dialog context index operations (compress/restore/windows/projects/doctor)
- `team` - team router selection/reset
- `evo` - evolution ledger views

## Quick start order

Use this order for a normal working session:

1. Check current windows/tree:
   - `/custom-rule: dci windows`
   - Effect: shows EV/DW structure for current repo and active window state.
2. If needed, switch or create window:
   - `/custom-rule: dci restore DW-001`
   - `/custom-rule: dci restore-new "summary"`
   - Effect: loads target dialog window context (delta-first).
3. Select team workflow:
   - `/custom-rule: team sql|b2c|de-matrix|web-app|presentation|auto`
   - Effect: locks chat to selected team routing until explicit reset.
4. Work in the session (implement/review/discuss).
5. Before handoff, compress context:
   - `/custom-rule: dci compress`
   - Effect: materialize + doctor + validate + sync + delta export + restore command for next chat.

## DCI commands and effects

- `/custom-rule: dci windows`
  - Shows project branch tree and dialog windows.
- `/custom-rule: dci projects`
  - Shows multi-project tree from registry/root.
- `/custom-rule: dci restore DW-NNN`
  - Restores a specific dialog window (delta mode).
- `/custom-rule: dci restore-new "summary"`
  - Creates and activates a new dialog window.
- `/custom-rule: dci materialize`
  - Builds reusable CP-* checkpoints from the active window state.
- `/custom-rule: dci compress`
  - Runs `materialize -> doctor -> validate -> sync/export` and prints handoff block:
    `restore: /custom-rule: dci restore DW-NNN`.
- `/custom-rule: dci expand CL-NNN` (or `EV-NNN`)
  - Opens explicit ledger body by ID.

## Team commands and effects

- `/custom-rule: team sql`
- `/custom-rule: team b2c`
- `/custom-rule: team de-matrix`
- `/custom-rule: team web-app`
- `/custom-rule: team presentation`
- `/custom-rule: team auto`
- `/custom-rule: team reset`

Effect:

- Selects or resets active team routing logic for the current chat.
- While team is locked, implicit auto-switching is disabled.

## Evolution commands and effects

- `/custom-rule: evo report`
- `/custom-rule: evo diff <EV-id|CL-id|topic>`
- `/custom-rule: evo branch-status`
- `/custom-rule: evo regress <EV-id|range|topic>`

Effect:

- Produces evolution-oriented views using EV/CL linkage without changing DCI window state.

## Recommended failure handling order

If DCI command fails:

1. Optionally run `/custom-rule: dci materialize` if you need explicit checkpoint build
2. Retry `/custom-rule: dci compress`
3. If embed backend is unavailable, run infra recovery:
   - `bash scripts/dci-vector.sh up`
   - then retry `/custom-rule: dci compress`
4. Use force only with explicit risk acceptance:
   - `bash scripts/dci-vector.sh compress --force`

## Worktree note

If the chat runs in a worktree (`~/.cursor/worktrees/...`) and DCI files are missing there, commands should not be improvised.

Expected behavior:

- report `DCI not deployed in this working copy`
- recover by opening the main checkout under `~/PycharmProjects/<project>` or by propagating rules from source.

Note: `doctor` exists as a debug-only fallback (`bash scripts/dci-vector.sh doctor`) and is normally executed internally by `compress`.
