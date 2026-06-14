---
name: b2c-team
description: Runs a structured multi-role review for SQL, Scala, Java, Spark, Hive, and HDFS pipelines with SQL plus Scala developer, Java or Scala developer, DBA, data engineer, analyst, tester, registry steward, reviewer, and arbiter. Use when user requests b2c-команда or cross-stack B2C pipeline validation.
disable-model-invocation: true
---

# B2C Team Workflow

## Trigger

Use this skill when the user explicitly selects `b2c-команда` or equivalent alias from the routing rule.

## Team Composition

- SQL plus Scala developer (Greenplum, PostgreSQL 9.4, Scala)
- Java or Scala developer
- DBA (Greenplum, PostgreSQL 9.4, Hive, HDFS)
- Data engineer (SQL, Spark, Scala, HDFS)
- Analyst
- Tester
- Registry Steward (ledger and traceability owner)
- Reviewer (independent expert)
- Arbiter

## Role Responsibilities

### SQL plus Scala Developer

Evaluate SQL and Scala implementation quality:
- syntax correctness and readability
- logging and observability
- maintainability of transformation logic
- optimization opportunities in SQL and Scala flows

### Java or Scala Developer

Evaluate JVM code quality:
- correctness and readability
- logging and error handling quality
- code structure and maintainability
- API and method-level design consistency

### DBA (Greenplum, PostgreSQL 9.4, Hive, HDFS)

Evaluate runtime and cluster pressure:
- cluster load risks and query-plan risks
- pipeline stability and fault tolerance
- worker and job allocation risks
- memory allocation and bottlenecks

### Data Engineer (SQL, Spark, Scala, HDFS)

Evaluate end-to-end data architecture:
- design of calculations, objects, and pipeline stages
- extraction and transformation strategies
- scale behavior and growth risks
- consistency across `ctl.yaml`, `mart.yaml`, classes, and methods
- variable reuse, config links, object references, and conflict prevention

### Analyst

Evaluate business fit:
- business logic correctness and integrity
- preservation of business meaning
- compliance with technical assignment
- documentation completeness and clarity

### Tester

Evaluate operational quality and regression safety:
- validate build health and absence of compile/package failures
- execute smoke checks (build verification) on critical flows before full regression
- execute confirmation and regression testing for every code/config change
- apply impact analysis to keep regression scope adequate and efficient
- select stand(s) from project context (file paths, environment markers, config files, deployment hints) and document rationale
- execute stand run on selected environment(s); if stand is ambiguous, ask one short clarification
- validate end-to-end flow integrity across SQL, Java, Scala, Spark, Hive, and HDFS stages
- run project functional tests for critical business and technical scenarios (happy path, negative path, degraded path)
- verify integrity of links/references between configs, classes, jobs, and objects
- verify variable integrity (declaration, reuse, shadowing/conflicts, and propagation through configs)
- validate data quality controls for marts: schema consistency, null handling, constraints, referential integrity, and source-to-target reconciliation
- ensure test coverage is balanced (broad unit/integration automation, targeted E2E checks)
- produce reproducible defect reports and retest outcomes

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

Perform independent assessment:
- identify cross-domain gaps
- validate assumptions and evidence
- ensure recommendations are coherent as one solution

### Arbiter

Resolve disputes and finalize decisions:
- mediate conflicting proposals
- issue final binding decisions with rationale
- guarantee full team agreement before closure
- summarize final implementation strategy

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

1. Each role submits findings with severity (`critical`, `major`, `minor`, `note`).
2. Team discusses disagreements and risks.
3. Tester provides stand selection, stand run result, and functional test result.
4. Tester issues QA gate (`pass`, `pass_with_risk`, `fail`) with blocking defects list.
5. Registry Steward initializes and/or updates `Q-*`, `CL-*`, `EV-*` and all links for new deltas.
6. Arbiter resolves each unresolved dispute.
7. Team confirms full consensus.
8. Return one consolidated result with clear next actions.

## Output Format

Return sections in this order:
1. `Selected Team: b2c-команда`
2. `Context Reuse` (reused IDs, updated IDs, challenged/confirmed IDs)
3. `Ledger Traceability` (`Q-*` to `CL-*` to `EV-*`)
4. `Evolution Snapshot` (`EV-*`, linked `CL-*`, branch states, key deltas)
5. `Role Findings` (delta-focused by role)
6. `Stand and Functional Test Results` (selected stand, scope, outcomes)
7. `QA Gate` (tester verdict and blocking defects)
8. `Disputes and Decisions` (arbiter resolutions)
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
