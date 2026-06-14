---
name: tig-snapshot
description: Generate and reuse TIG context artifacts (compact snapshot + git diff delta) for architecture, evolution, and token-efficient agent context.
---
# TIG Snapshot for Cursor (v1.5)

## Goal
Low-token project map (`.cursor/context/tig/tig_snapshot.md`) + accurate evolution via **git diffs** (`.cursor/context/tig/tig_delta.md`).

## Commands

**Preflight:**
```bash
bash .cursor/tools/tig/bin/tig-context.sh "." "origin/main"
```

**Postflight (fast — reuse snapshot, refresh diffs):**
```bash
bash .cursor/tools/tig/bin/tig-context.sh "." "origin/main" --delta-only
```

Validation: `bash .cursor/tools/tig/bin/tig-test.sh`

## Agent read order (mandatory)

1. `.cursor/context/tig/tig_delta.md` — commits, changed files, **Unified diff vs base ref**, working tree diff
2. `.cursor/context/tig/tig_snapshot.md` — only:
   - `## Module map`
   - `## Directory tree`
   - `## File index (compressed)`
3. Direct file reads — paths from delta diff only

**Do not** paste full snapshot into chat.

## Artifacts

| File | Content | Reuse |
|------|---------|-------|
| `.cursor/context/tig/tig_snapshot.md` | module map, tree (depth≤2), capped file index | fingerprint reuse |
| `.cursor/context/tig/tig_delta.md` | git log, name-status, unified diff (≤2500 lines) | always refresh |

Base ref fallback: `origin/main` → `main` → `HEAD~1` → `HEAD`.

## Workflow
1. Preflight: snapshot + delta
2. Plan from delta (diffs) + module map
3. Implement
4. Postflight: `--delta-only`
5. Summarize impact from refreshed delta

## Escalation
Deep audit with file bodies:
```bash
python3 tig_app_ru.py --cli --target "." --out tig_snapshot_changed.md --full --changed-only --snapshot-base-ref origin/main
```

## Notes
- Compact snapshot target: ≤800 lines (module map + tree + capped index)
- Excludes `.env*`, `tig_snapshot*`, `tig_delta*` by default
- Git is source of evolution; do not accumulate snapshot versions
