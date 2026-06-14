# DCI v9: тест-кейсы функционала и операций

Документ: DCI v9 (handoff, delta-first, validate gate, local embed server).  
Стенд: repo `gp_dq`, pgvector Docker `:5433`, embed server `:18081`, `.venv/bin/python`.

## Предусловия (общие)

| # | Условие | Проверка |
|---|---------|----------|
| P0 | Docker pgvector запущен | `bash .cursor/tools/dci/bin/dci-vector.sh status` → `pgvector: ok` |
| P0b | Embed server (semantic pass) | `status` → `tei: ok`; `DCI_EMBED_URL` в `dci.env`; `dci-vector.sh up` |
| P1 | `DCI_PROJECT_ID=gp_dq` в `.cursor/dci/dci.env` | совпадает с repo |
| P2 | `.cursor/context/.project_lock` | `project_id: gp_dq` |
| P3 | `.cursor/context/project_catalog.md` | существует |
| P4 | `.cursor/context/dialogs/DW-001/dialog_index.md` | существует, без `### EV` |
| P5 | Python venv | `.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py status` → exit 0 |

**Teardown после destructive-кейсов:** восстановить `.dialog_window_lock` = `DW-001`, `active_window: DW-001` в catalog.

---

## Матрица кейсов (summary)

| ID | Категория | Приоритет | Auto | Кратко |
|----|-----------|-----------|------|--------|
| TC-OPS-01 | Operations | P0 | Y | status — guards + DB ping |
| TC-OPS-02 | Operations | P0 | Y | up — container + sync --all |
| TC-OPS-03 | Operations | P1 | Y | migrate — fallback → pgvector |
| TC-PRJ-01 | Project scope | P0 | Y | project mismatch → exit 2 |
| TC-PRJ-02 | Project scope | P0 | Y | cross-project import → exit 2 |
| TC-DW-01 | Window scope | P0 | Y | window env mismatch → exit 2 |
| TC-DW-02 | Window scope | P0 | Y | cross-window import → exit 2 |
| TC-DW-03 | Window scope | P0 | Y | lookup не смешивает DW |
| TC-CAT-01 | Catalog | P0 | Y | catalog — branches + windows + summary |
| TC-CAT-02 | Catalog | P1 | Y | catalog --branches / --windows |
| TC-REST-01 | Restore | P0 | Y | restore DW-001 — lock + sync |
| TC-REST-02 | Restore | P0 | Y | restore DW-002 — switch active window |
| TC-WNEW-01 | Window new | P1 | Y | window-new — alloc DW-NNN + index |
| TC-SI-01 | Structured index | P0 | Y | window index без EV table |
| TC-SI-02 | Structured index | P0 | Y | EV/CP только в project_catalog |
| TC-SI-03 | Structured index | P1 | Y | legacy pointer dialog_index.md |
| TC-VI-01 | Vector DB | P0 | Y | sync window → namespace gp_dq/DW-NNN |
| TC-VI-02 | Vector DB | P0 | Y | sync --project → gp_dq/__project__ |
| TC-VI-03 | Vector DB | P0 | Y | lookup window scope hybrid |
| TC-VI-04 | Vector DB | P0 | Y | lookup --project для EV/CP |
| TC-VI-05 | Vector DB | P1 | Y | cleanup stale namespaces |
| TC-DB-01 | DB R/W | P0 | Y | sync пишет row в pgvector (upsert) |
| TC-DB-02 | DB R/W | P0 | Y | SQL read — content/metadata совпадает с index |
| TC-DB-03 | DB R/W | P0 | Y | lookup извлекает ту же запись из БД (round-trip) |
| TC-IO-01 | Import/Export | P0 | Y | export — archive bundle mirror |
| TC-VAL-01 | Validate gate | P0 | Y | validate — pass on DW-001 |
| TC-HO-01 | Handoff | P0 | Y | compress — handoff_ready + restore cmd |
| TC-HO-02 | Handoff | P0 | Y | restore — load_mode delta |
| TC-EMB-01 | Embeddings | P0 | Y* | lookup RU query → CL-007 (*TEI up) |
| TC-EMB-02 | Embeddings | P0 | Y* | negative lookup (*TEI up) |
| TC-EMB-03 | Incremental | P0 | Y | compress snapshot exists |
| TC-AGENT-01 | Agent policy | P1 | M | session start — validate locks |
| TC-AGENT-02 | Agent policy | P1 | M | restore не подмешивает EV |
| TC-AGENT-03 | Agent policy | P0 | Y | accompaniment v2 block in compress/restore |
| TC-REG-01 | Regression | P0 | Y | v7→v9 DW-001 + catalog + delta |

**Auto:** Y = shell/python, M = manual (agent/rule behaviour).

---

## TC-OPS — Operations

### TC-OPS-01 — status (guards + DB)

**Pre:** P0–P5.

```bash
cd /path/to/gp_dq
bash .cursor/tools/dci/bin/dci-vector.sh status
```

**Expected:**
- exit 0
- `project_id: gp_dq`
- `dialog_window_id: DW-001` (или active lock)
- `lock_project_id: gp_dq`, `lock_window_id` совпадает
- `vector_namespace: gp_dq/DW-001`
- `project_namespace: gp_dq/__project__`
- `pgvector: ok`

---

### TC-OPS-02 — up (cold start)

**Pre:** `bash .cursor/tools/dci/bin/dci-vector.sh down` (optional).

```bash
bash .cursor/tools/dci/bin/dci-vector.sh up
```

**Expected:**
- container `gp_dq_dci_pgvector` healthy
- sync `--all` completes without error
- embeddings present in pgvector

---

### TC-OPS-03 — migrate

**Pre:** P0, есть rows в `vector_fallback.jsonl` с `synced_to_db: false` (optional).

```bash
bash .cursor/tools/dci/bin/dci-vector.sh migrate
```

**Expected:**
- exit 0
- `migrated N row(s)` (N ≥ 0)
- pending_ids → none в meta после sync

---

## TC-PRJ — Project isolation

### TC-PRJ-01 — project mismatch guard

```bash
DCI_PROJECT_ID=other_project .venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py status
echo exit:$?
```

**Expected:**
- stderr: `ERROR scope mismatch ... index=gp_dq current=other_project`
- exit 2

---

### TC-PRJ-02 — cross-project import

```bash
printf 'project_id: other\n' > /tmp/fake_bundle.md
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py import --source /tmp/fake_bundle.md
echo exit:$?
```

**Expected:**
- `cross-project import forbidden`
- exit 2
- `dialogs/*/dialog_index.md` не изменён

---

## TC-DW — Dialog window isolation

### TC-DW-01 — window env mismatch

```bash
DCI_DIALOG_WINDOW_ID=DW-999 .venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py status
echo exit:$?
```

**Expected:**
- `window_lock=DW-001 current=DW-999` (или аналог)
- exit 2

---

### TC-DW-02 — cross-window import

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py import \
  --source .cursor/context/dialogs/DW-002/dialog_bundle.md \
  --window DW-001
echo exit:$?
```

**Expected:**
- `cross-window import forbidden: source=DW-002 target=DW-001`
- exit 2

---

### TC-DW-03 — lookup isolation между окнами

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py lookup --query "UAT special"
# top hits — DCI/Global rules, NOT "UAT special_dq_2"

bash .cursor/tools/dci/bin/dci-vector.sh restore DW-002
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py lookup --query "UAT special"
# top hits — Q-001/TH-001 "UAT special_dq_2 test window"
```

**Expected:**
- namespace в выводе: `gp_dq/DW-001` vs `gp_dq/DW-002`
- результаты не пересекаются по content

**Post:** `bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001`

---

## TC-CAT — Catalog

### TC-CAT-01 — full catalog

```bash
bash .cursor/tools/dci/bin/dci-vector.sh catalog
```

**Expected:**
- `## Branches (project)` — EV-PROJECT, EV-001 с summary
- `## Windows (dialogs)` — DW-001, DW-002 с summary, `*` на active_window
- exit 0

---

### TC-CAT-02 — filtered catalog

```bash
bash .cursor/tools/dci/bin/dci-vector.sh catalog --branches
bash .cursor/tools/dci/bin/dci-vector.sh catalog --windows
```

**Expected:**
- `--branches`: только EV table
- `--windows`: только DW table

---

## TC-REST / TC-WNEW — Restore & window new

### TC-REST-01 — restore DW-001

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
```

**Expected:**
- `restored active window: DW-001`
- `summary: Global rules, skills, DCI design`
- `.dialog_window_lock` → `DW-001`
- `project_catalog.md` → `active_window: DW-001`
- sync namespace `gp_dq/DW-001` ok

---

### TC-REST-02 — restore DW-002 (switch)

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-002
cat .cursor/context/.dialog_window_lock
```

**Expected:**
- lock = `DW-002`
- catalog `active_window: DW-002`
- `hot_open: TH-001` (если есть в index)

**Post:** restore DW-001

---

### TC-WNEW-01 — window-new

```bash
bash .cursor/tools/dci/bin/dci-vector.sh window-new "Test window TC-WNEW-01"
```

**Expected:**
- новый `DW-NNN` (следующий после max)
- `dialogs/DW-NNN/dialog_index.md` с Q-001, TH-001 open
- запись в `window_registry` catalog
- bundle exported
- vectors в `gp_dq/DW-NNN`

---

## TC-SI — Structured Index

### TC-SI-01 — window index без EV

```bash
grep -n '^### EV' .cursor/context/dialogs/DW-001/dialog_index.md; echo exit:$?
```

**Expected:** grep exit 1 (нет совпадений).

---

### TC-SI-02 — EV/CP в catalog

```bash
grep '## branch_registry' -A5 .cursor/context/project_catalog.md
grep '## checkpoint_registry' -A3 .cursor/context/project_catalog.md
```

**Expected:** EV-PROJECT, EV-001, CP-001..CP-007 present.

---

### TC-SI-03 — legacy pointer

```bash
head -6 .cursor/context/dialog_index.md
```

**Expected:**
- `deprecated: use project_catalog.md`
- `active_window: DW-001`
- `see: .cursor/context/project_catalog.md`

---

## TC-VI — Vector DB

### TC-VI-01 — sync window namespace

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py sync --migrate
.venv/bin/python -c "
import psycopg2
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"SELECT count(*) FROM dci_embeddings WHERE dialog_id='gp_dq/DW-001'\")
print('DW-001 count:', cur.fetchone()[0])
"
```

**Expected:** count ≥ 1 (после sync ledgers).

---

### TC-VI-02 — sync project namespace

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py sync --migrate --project
.venv/bin/python -c "
import psycopg2
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"SELECT count(*) FROM dci_embeddings WHERE dialog_id='gp_dq/__project__'\")
print('__project__ count:', cur.fetchone()[0])
"
```

**Expected:** count ≥ 1 (EV + CP).

---

### TC-VI-03 — lookup window (hybrid)

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
bash .cursor/tools/dci/bin/dci-vector.sh lookup "DCI v8"
```

**Expected:**
- `access: hybrid`
- `namespace=gp_dq/DW-001`
- CL-007 или related in top hits

---

### TC-VI-04 — lookup project EV

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py lookup --query "DCI evolution" --project
```

**Expected:**
- `scope=project`, `namespace=gp_dq/__project__`
- EV-001 in top hits

---

### TC-VI-05 — stale namespace cleanup

**Pre:** вручную INSERT row с `dialog_id='gp_dq'` (legacy v7 format) или `other/DW-001`.

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py sync --migrate --all
.venv/bin/python -c "
import psycopg2
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"SELECT dialog_id FROM dci_embeddings WHERE dialog_id NOT LIKE 'gp_dq/%'\")
print('orphans:', cur.fetchall())
"
```

**Expected:**
- sync log: `cleaned stale vector namespaces`
- orphans = [] (только `gp_dq/*` namespaces)

---

## TC-DB — Запись в БД и извлечение

### TC-DB-01 — upsert при sync (write)

**Pre:** P0, active window DW-001.

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py sync --migrate
.venv/bin/python -c "
import psycopg2
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"\"\"
  SELECT ledger_id, ledger_type, dialog_id, source, length(content)>0 AS has_content
  FROM dci_embeddings
  WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
\"\"\")
row=cur.fetchone()
print('CL-007 row:', row)
assert row and row[1]=='CL' and row[2]=='gp_dq/DW-001' and row[4], 'upsert failed'
"
```

**Expected:**
- row exists for `CL-007` in `gp_dq/DW-001`
- `has_content = true`, `source` = `hash_embed:384` or `openai:*`
- `dci_sync_log` содержит action `upsert` (optional check)

---

### TC-DB-02 — прямое чтение content/metadata (read)

```bash
.venv/bin/python -c "
import psycopg2, json
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"\"\"
  SELECT content, metadata->>'project_id', metadata->>'scope', metadata->>'dialog_window_id'
  FROM dci_embeddings
  WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
\"\"\")
content, pid, scope, dw = cur.fetchone()
print('content snippet:', content[:60])
print('meta:', pid, scope, dw)
assert 'v8' in content.lower() or 'window' in content.lower()
assert pid=='gp_dq' and scope=='window' and dw=='DW-001'
"
```

**Expected:**
- content содержит текст из `dialogs/DW-001/dialog_index.md` (CL-007 scope)
- metadata: `project_id=gp_dq`, `scope=window`, `dialog_window_id=DW-001`

---

### TC-DB-03 — round-trip: sync → lookup → сверка с БД

```bash
bash .cursor/tools/dci/bin/dci-vector.sh lookup "dialog window sub-isolation" > /tmp/dci_lookup.out
.venv/bin/python -c "
import psycopg2
hits=open('/tmp/dci_lookup.out').read()
assert 'CL-007' in hits, 'lookup must return CL-007'
c=psycopg2.connect(host='localhost',port=5433,dbname='dci_vectors',user='dci',password='dci_local')
cur=c.cursor()
cur.execute(\"\"\"
  SELECT ledger_id, left(content,80)
  FROM dci_embeddings
  WHERE dialog_id='gp_dq/DW-001' AND ledger_id='CL-007'
\"\"\")
lid, content = cur.fetchone()
assert lid=='CL-007'
assert 'sub-isolation' in content.lower() or 'v8' in content.lower()
print('round-trip OK:', lid, content[:50])
"
```

**Expected:**
- lookup (hybrid) возвращает `CL-007` in top hits
- SQL read того же `ledger_id` — content согласован с lookup summary

**Project namespace (optional):**

```bash
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py lookup --query "DCI evolution" --project > /tmp/dci_ev.out
grep EV-001 /tmp/dci_ev.out
# SQL: dialog_id='gp_dq/__project__' AND ledger_id='EV-001'
```

---

## TC-IO — Import / Export

### TC-IO-01 — export active window

```bash
bash .cursor/tools/dci/bin/dci-vector.sh export
wc -l .cursor/context/dialogs/DW-001/dialog_index.md \
       .cursor/context/dialogs/DW-001/dialog_bundle.md
```

**Expected:**
- bundle содержит `project_id`, `dialog_window_id`, `exported_at`
- body bundle ≥ index lines (full mirror)

---

### TC-IO-02 — import same window

```bash
bash .cursor/tools/dci/bin/dci-vector.sh export
bash .cursor/tools/dci/bin/dci-vector.sh import .cursor/context/dialogs/DW-001/dialog_bundle.md
```

**Expected:** exit 0, index unchanged по смыслу, sync ok.

---

### TC-IO-03 — export non-active window

```bash
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
.venv/bin/python .cursor/tools/dci/lib/dci_vector_sync.py export --window DW-002
```

**Expected:**
- exit 0 (не требует switch lock на DW-002)
- bundle written to `dialogs/DW-002/dialog_bundle.md`
- lock остаётся DW-001

---

## TC-AGENT — Agent / rule policy (manual)

### TC-AGENT-01 — session bootstrap

**Steps:**
1. Открыть новый agent chat в repo `gp_dq`.
2. Agent должен (по rule): load catalog/window index, run `dci-vector.sh status`.

**Expected:**
- при mismatch — agent **не** загружает foreign ledgers
- сообщает exit 2 / refuse policy

---

### TC-AGENT-02 — restore без EV auto-load

**Steps:**
1. `/custom-rule: dci restore DW-001`
2. Проверить accompaniment block.

**Expected:**
- `window: DW-001`, `master: EV-PROJECT`
- EV-* — только catalog refs, без full expand EV-001 body
- expand EV только по `/custom-rule: dci expand EV-001`

---

### TC-AGENT-03 — accompaniment v2 (auto + manual)

**Auto:**
```bash
bash .cursor/tools/dci/bin/dci-vector.sh compress --force | grep -E 'project:|load_mode:|handoff_ready:'
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001 | grep -E 'project:|load_mode:|embed_backend:'
```

**Expected block (between `---` markers):**
- `project: gp_dq`
- `window: DW-NNN`
- `master: EV-PROJECT`
- `load_mode: delta|restore`
- `changed: …|none`
- `handoff_ready: true|false`
- `access: hybrid|structured-only`
- `embed_backend: tei:*|openai:*|hash_embed:*`

---

## TC-REG — Regression

### TC-REG-01 — regression v7 → v9

**Checks:**
- `dialogs/DW-001/dialog_index.md` содержит Q-001, CL-001..007, TH-001
- EV-секция **только** в `project_catalog.md`
- root `dialog_index.md` — pointer only
- CL-006 (v7 isolation) + CL-007 (v8 windows) + CL-008+ (v9 handoff/delta) active when present
- root pointers — v9 deprecated stubs
- `dialogs/DW-001/dialog_delta.md` — handoff_ready after compress

**Expected:** все checks pass.

---

## Smoke-прогон (5 мин)

```bash
bash .cursor/tools/dci/bin/dci-vector.sh status
bash .cursor/tools/dci/bin/dci-vector.sh validate
bash .cursor/tools/dci/bin/dci-vector.sh windows
bash .cursor/tools/dci/bin/dci-vector.sh compress --force
bash .cursor/tools/dci/bin/dci-vector.sh restore DW-001
bash .cursor/tools/dci/bin/dci-vector.sh lookup "DCI"
bash .cursor/tools/dci/bin/dci-test.sh
```

**Pass criteria:** все exit codes и outputs как в кейсах TC-OPS-01, TC-CAT-01, TC-VI-03/04, TC-PRJ-01, TC-DW-01.

---

## TC-HO / TC-VAL / TC-EMB — DCI v9 (auto)

| ID | Case | Expected |
|----|------|----------|
| TC-VAL-01 | `dci-vector.sh validate` | `validate: pass` on DW-001 |
| TC-HO-01 | `compress --force` | `handoff_ready: true` + restore command |
| TC-HO-02 | `restore DW-001` | `load_mode: delta` |
| TC-EMB-01 | lookup + TEI up | top hit CL-007 for RU query |
| TC-EMB-02 | negative lookup | UAT query not top1 CL-007 |
| TC-EMB-03 | after compress | `.compress_snapshot.json` exists |

---

## QA Gate

| Verdict | Условие |
|---------|---------|
| **pass** | все P0 auto-кейсы green |
| **pass_with_risk** | P0 green, P1/P2 ≤2 open с documented workaround |
| **fail** | любой P0 red или guard не exit 2 |
