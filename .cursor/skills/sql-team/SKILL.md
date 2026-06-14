---
name: sql-team
description: Runs a structured multi-role SQL review for Greenplum and PostgreSQL 9.4 with SQL developer, data engineer, analyst, DBA, tester, registry steward, reviewer, and arbiter. Use when user requests sql-команда, SQL review, SQL pipeline design review, or cross-functional SQL validation.
disable-model-invocation: true
---

# SQL Team Workflow

## Trigger

Use this skill when the user explicitly selects `sql-команда` or equivalent alias from the routing rule.

## Team Composition

- SQL developer (Greenplum, PostgreSQL 9.4)
- Data engineer
- Analyst
- DBA (Greenplum, PostgreSQL 9.4)
- Tester
- Registry Steward (ledger and traceability owner)
- Reviewer (independent expert)
- Arbiter

## Role Responsibilities

### SQL Developer

Evaluate SQL quality:
- correctness of syntax for Greenplum and PostgreSQL 9.4
- readability and maintainability
- logging and observability points
- naming, structure, and code clarity
- query-level optimization opportunities

### Data Engineer

Evaluate solution architecture:
- design of calculations and SQL objects
- extraction and transformation approach
- pipeline architecture and dependency flow
- scalability risks with data growth
- compatibility with SQL optimization proposals

### Analyst

Evaluate business alignment:
- business logic correctness
- preservation of business meaning
- compliance with technical assignment
- adequacy of documentation and traceability

### DBA

Evaluate platform reliability:
- cluster load risks
- expected query plan risks and anti-patterns
- throughput and stability constraints
- operational resilience of the pipeline

### Tester

Evaluate quality gate readiness and defect risk:
- verify build readiness and smoke checks (build verification test) before deep testing
- run confirmation checks for fixes and regression checks after every change
- use impact analysis to scope regression coverage efficiently
- select test stand(s) from project file context (paths, configs, env markers) and record the selection rationale
- execute stand run on selected environment(s); if stand cannot be inferred from context, ask one short clarification
- validate functional behavior, negative paths, and edge cases
- run project functional tests on critical user and data scenarios, including happy path and key failure paths
- verify SQL object integrity, reference/link integrity, and variable integrity across scripts and configs
- check data quality controls: schema consistency, null/constraint checks, and referential integrity
- ensure automated checks fit a balanced strategy (many unit checks, targeted integration checks, minimal E2E checks)
- produce clear defect reports with severity, reproduction, expected vs actual, and retest status

### Registry Steward

Own dialog-scoped memory and change traceability:
- maintain `Q-*` (processed questions), `CL-*` (conclusions), and `EV-*` (evolution items)
- enforce links `Q-* -> CL-* -> EV-*` for each meaningful update
- track diffs/deltas, key points, and impacted artifacts per `EV-*`
- tag every evolution item by domain: `sql`, `b2c`, or `cross-domain`
- track branch states (`active`, `in_progress`, `merged`, `dead`) with reasons and replacements
- keep summaries token-efficient: reuse IDs and provide delta-first updates
- run semantic lookup only when enabled, otherwise keep structured-ledger mode

### Reviewer

Perform independent end-to-end critique:
- surface blind spots not covered above
- challenge weak assumptions
- verify evidence quality for conclusions

### Arbiter

Resolve all role disputes and finalize consensus:
- collect conflicting recommendations
- choose final decision with clear rationale
- ensure no blocking disagreement remains
- summarize final agreed implementation path

## Token-Efficient Reuse Protocol

Maintain a short `Conclusion Ledger` in the response flow:
- assign IDs: `CL-001`, `CL-002`, ...
- reference IDs for reused conclusions instead of repeating full text
- update only impacted conclusions when new evidence appears
- if user asks to challenge, provide counter-arguments and verdict per targeted ID
- if user asks to confirm, verify assumptions and mark IDs as confirmed or revised

## Project Evolution Protocol

Maintain `Project Evolution Ledger` linked to conclusions:
- assign evolution IDs: `EV-001`, `EV-002`, ...
- connect each evolution item to relevant `CL-*` IDs and question/topic
- store delta summary, changed artifacts, and key technical points
- set evolution domain on each item: `sql`, `b2c`, or `cross-domain`
- track branch state per affected workstream: `active`, `in_progress`, `merged`, `dead`
- for `dead` branches, record closure reason and replacement branch/path
- for `in_progress` branches, record open risks, missing checks, and next checkpoint

## Semantic Memory Protocol (optional)

Chosen strategy is hybrid:
- default: structured dialog ledgers only (`Q-*`, `CL-*`, `EV-*`)
- optional semantic layer for long history or imports
- preferred backend: `pgvector` with metadata filters
- embedding baseline: `text-embedding-3-small`
- use semantic retrieval only when explicitly enabled by user intent

## Collaboration Protocol

1. Each role publishes findings with severity (`critical`, `major`, `minor`, `note`).
2. Team discusses conflicts between roles.
3. Tester provides stand selection, stand run result, and functional test result.
4. Tester issues QA gate (`pass`, `pass_with_risk`, `fail`) with blocking defects list.
5. Registry Steward initializes and/or updates `Q-*`, `CL-*`, `EV-*` and all links for new deltas.
6. Arbiter resolves every unresolved conflict.
7. Team reaches explicit final consensus.
8. Return a single consolidated result.

## Output Format

Return sections in this order:
1. `Selected Team: sql-команда`
2. `Context Reuse` (reused IDs, updated IDs, challenged/confirmed IDs)
3. `Ledger Traceability` (`Q-*` to `CL-*` to `EV-*`)
4. `Evolution Snapshot` (`EV-*`, linked `CL-*`, branch states, key deltas)
5. `Role Findings` (delta-focused by role)
6. `Stand and Functional Test Results` (selected stand, scope, outcomes)
7. `QA Gate` (tester verdict and blocking defects)
8. `Disputes and Decisions` (arbiter decisions)
9. `Final Consensus`
10. `Action Plan` (ordered, concrete steps)

## Context Reuse Mini Template (mandatory when overlap exists)

Use this compact structure:

```markdown
### Context Reuse
- reused: <CL-ids or none>
- updated: <CL-id -> new status/reason, or none>
- challenged: <CL-ids + outcome, or none>
- confirmed: <CL-ids + evidence, or none>
- superseded: <old CL-id -> new CL-id, or none>
```

## Ledger Traceability Mini Template (mandatory)

Use this compact structure:

```markdown
### Ledger Traceability
- dialog_scope: <current-dialog-window>
- questions: <Q-ids touched in this response>
- links: <Q-id -> CL-id(s) -> EV-id(s)>
- new_ids: <new Q/CL/EV ids or none>
- remapped_ids: <old id -> new id, if superseded>
```

## Evolution Mini Template (mandatory when change history matters)

Use this compact structure:

```markdown
### Evolution Snapshot
- ev_id: <EV-id>
- linked_conclusions: <CL-ids or none>
- linked_questions: <Q-ids or none>
- domain: <sql|b2c|cross-domain>
- scope: <files/components/pipeline scope>
- delta: <what changed since previous state>
- key_points: <1-3 key technical points>
- branch_state: <active|in_progress|merged|dead>
- branch_note: <reason/status, for dead include closure reason; for in_progress include blockers>
- regression_focus: <areas that require regression checks>
```

## Tester Mini Template (mandatory)

Use this exact structure for tester output:

```markdown
### Tester Report

Stand:
- selected: <stand-name>
- rationale: <why this stand was selected from project context>

Build and Smoke:
- build status: <pass|fail|not_run>
- smoke status: <pass|fail|not_run>
- evidence: <short logs/checks summary>

Functional Testing:
- scope: <critical scenarios covered>
- result: <pass|fail|partial>
- failed scenarios: <list or none>

Regression and Integrity:
- regression scope: <changed areas and impacted areas>
- regression result: <pass|fail|partial>
- links/references integrity: <ok|issues>
- variables integrity: <ok|issues>
- data integrity checks: <ok|issues>

Defects:
- blocking: <count + ids/summary>
- non_blocking: <count + ids/summary>

QA Gate:
- verdict: <pass|pass_with_risk|fail>
- release recommendation: <go|go_with_risk|no_go>
- required actions: <ordered list>
```
