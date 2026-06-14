---
name: dialog-context-index
description: DCI v9 — handoff memory protocol, delta-first load, local embed server, validate gate.
disable-model-invocation: true
---

# Dialog Context Index (DCI) — User Protocol v9

Trigger: `.cursor/rules/dialog-context-index.mdc`.

## Four user commands

### 1. `/custom-rule: dci compress`

**Pipeline:**
1. `bash .cursor/tools/dci/bin/dci-vector.sh materialize` (internal, via compress)
2. `bash .cursor/tools/dci/bin/dci-vector.sh doctor` (internal, via compress)
3. `bash .cursor/tools/dci/bin/dci-vector.sh validate` (internal, via compress)
4. compute delta vs last snapshot → `dialog_delta.md`
5. sync project EV/CP + active window (incremental embed)
6. export bundle (`archive: true`, not default load)
7. **handoff block** for new chat

**Agent must output after compress** (script prints block; agent copies `---` section):

```
handoff_ready: true
next_chat: откройте новый Cursor chat
restore: /custom-rule: dci restore DW-NNN
---
project: …
window: …
load_mode: delta
handoff_ready: true
access: …
---
```

**Memory contract:** реальное снижение tokens — только в **новом chat** + restore. Текущий chat IDE не очищается.

**Output contract:** `/custom-rule: dci compress` выводит **только** stdout скрипта (`---` блок + `restore:`). Запрещены ручные таблицы `Conclusion Ledger` / `Project Evolution Ledger` / «Сводка контекста» как результат compress. In-chat `CL-*`/`EV-*` сначала записываются в `dialog_index.md`/`project_catalog.md`, затем фиксируются скриптом. На `validate: fail` — блокеры + recovery, без импровизированной сводки.

**Agent runs (only):**
```bash
bash .cursor/tools/dci/bin/dci-vector.sh compress
```

**Forbidden:**
- заменять compress ручной «выжимкой» из index/bundle;
- вызывать `compress --force` без явного согласия пользователя на `pass_with_risk`.

**On exit 1 (hash_embed / embed down):** сообщить блокер + шаги recovery (`bash .cursor/tools/dci/bin/dci-vector.sh up` → retry). Не ретраить с `--force` молча.

**Restore (`/custom-rule: dci restore DW-NNN`):**
```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-NNN
```
Запускать с **full permissions** — иначе падение на записи `.dialog_window_lock`. После success: delta + accompaniment; bundle не грузить.

---

### 2. `/custom-rule: dci windows` / `/custom-rule: dci projects`

Tree format (mandatory labels):

`DW-NNN | name: «…» | desc: «…» | [slot][lifecycle]`

**Multi-project:** shared pgvector `:5433`; isolation by `dialog_id={project_id}/DW-NNN`. Each repo has `DCI_PROJECT_ID` + local locks (gitignored). `projects.registry` or `DCI_PROJECTS_ROOT` builds full tree.

Validate all repos: `bash .cursor/tools/dci/bin/dci-validate-all-projects.sh`

---

## Multi-project isolation (shared pgvector)

- **One stack** for all repos: pgvector Docker `:5433` + **local Python embed server** `:18081` (`.cursor/tools/dci/lib/dci_embed_server.py`, started by `dci-vector.sh up`); data isolated by `dialog_id` namespace: `{project_id}/DW-NNN` and `{project_id}/__project__`.
- Each repo: `DCI_PROJECT_ID=<folder>` in `.cursor/dci/dci.env`; runtime locks/fallback **per repo** (gitignored).
- **`/custom-rule: dci projects`:** `.cursor/dci/projects.registry` or `DCI_PROJECTS_ROOT` — tree project → branches → dialogs; no cross-project window mix.
- **Forbidden:** sync/cleanup in project A must not delete vectors of project B (project-scoped cleanup only).

---

### 3. `/custom-rule: dci restore DW-NNN`

**Slim restore** — источник: `dialog_index.md` + **`dialog_delta.md`**, не bundle.

**Agent reads:** delta `changed_ids`, `hot_open` rows from index, hydrate lookup (top-3 from script output).

**Output includes:**
```
load_mode: delta
delta: …/dialog_delta.md
archive_bundle: … (do not load by default)
expand: /custom-rule: dci expand CL-NNN | EV-NNN
```

---

### 4. Context load modes

| Mode | Read |
|------|------|
| `delta` | `dialog_delta.md` only + CL-* IDs from delta |
| `restore` | delta + index rows for `changed_ids`/`hot_open` + hydrate ≤3 |
| `expand` | explicit CL/EV body |

**Forbidden after compress:** read `dialog_bundle.md`, paste full index or full `ledger_map`.

---

## Token read budget

Agent load policy (mandatory):

| Situation | Load |
|-----------|------|
| Default turn (no `/custom-rule: dci ...`) | **Nothing** from DCI |
| Code/repo question | TIG: `.cursor/context/tig/tig_delta.md` → targeted `.cursor/context/tig/tig_snapshot.md` sections |
| `delta` mode | `dialog_delta.md` only; cite CL-* by ID, no index paste |
| `restore` mode | delta + `lookup_index`/`hot_open` rows for `changed_ids` only; hydrate ≤3 from script output |
| `expand` | single CL/EV body on explicit user request |

**Real token savings:** handoff to **new chat** + slim restore. Current IDE chat is not cleared automatically.

**Never default-load:** `dialog_bundle.md` (archive), full `ledger_map`, full index table in agent reply.

---

## Local embeddings (accuracy)

Stack: **local embed server** (`.cursor/tools/dci/lib/dci_embed_server.py`, TEI-compatible API on `:18081`) → OpenAI (optional) → hash_embed (warn/fail on compress without `--force`).

Config: `.cursor/dci/dci.env` — `DCI_EMBED_URL=http://localhost:18081/embed`

Start: `bash .cursor/tools/dci/bin/dci-vector.sh up` (pgvector + embed server + auto re-embed on backend upgrade)

---

## Latency (expected)

`compress` / `restore` are **not instant** — normal 10–60 s when pgvector is warm; first run or cold Docker can take longer.

| Factor | Effect |
|--------|--------|
| `compress` | validate + sync project + sync window + export + delta write |
| `restore` | sync window (+ hydrate if `hot_open`) |
| pgvector cold / Docker waking | TCP wait; capped by `connect_timeout=3` → fast fallback |
| sandbox → retry with `all` | extra perceived delay; restore: use `all` immediately |
| embed server not running | compress fails fast (no localhost probe) |

Agent: after starting script, tell user «DCI sync running…»; do not treat silence as hang until ~90 s.

---

## Ledger integrity invariant (architectural, reusable)

Унифицированный подход для любого Cursor-проекта: DCI-ledger всегда validate-safe.

| Layer | Owner | Mechanism |
|------|-------|-----------|
| Creation | `dci-propagate.sh` bootstrap / `restore-new` | valid template (open TH + next_action + open_risks) |
| Self-heal | core `cmd_doctor` (`bash .cursor/tools/dci/bin/dci-vector.sh doctor`) | idempotent fix of V-01/V-02 on open TH; no-op when clean |
| Gate | `cmd_compress` | auto-`materialize` + auto-`doctor` → re-validate; residual fail → blockers + recovery |
| Propagation | `dci-propagate.sh::repair_bootstrap_ledger` | calls target core `doctor` (single source of truth) |

`/custom-rule: dci materialize` → `bash .cursor/tools/dci/bin/dci-vector.sh materialize`. Строит CP-* из текущего состояния окна (open TH/risk) и делает контекст переиспользуемым в handoff.

`doctor` = debug-only fallback (`bash .cursor/tools/dci/bin/dci-vector.sh doctor`) для инженерной диагностики. В обычном пользовательском потоке не требуется: `compress` вызывает `doctor` автоматически.

## Bounded accuracy contract

Guaranteed only for:
- Records in Q/CL/TH ledgers
- `evidence` files that exist (validate V-04)
- Semantic retrieval when backend is `tei:*` or `openai:*`

Outside ledger → `open_risks`; not auto-restored.

---

## Quality gate

After `сжать`: `validate: pass`, `pending=0`, `handoff_ready: true`, restore command present.

Verdict `pass` required.
