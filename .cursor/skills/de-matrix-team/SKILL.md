---
name: de-matrix-team
description: Builds and reviews a senior-level data engineering competency matrix for attestation using a cross-functional panel of data engineer, devops, dataops, dba, sql engineer, etl or elt engineer, scala python spark engineer, hadoop engineer, reviewer, technical writer, arbiter, and registry steward. Use when user requests de-matrix-команда, competency matrix design, or attestation matrix work.
disable-model-invocation: true
---

# DE Matrix Team Workflow

## Trigger

Use this skill when the user explicitly selects `de-matrix-команда` or equivalent alias from the routing rule.

## Mandatory Reference Documents

Before designing or revising any matrix content, the team must use both documents as primary guidance:
- `exls_matrix/matrix_methodology.md`
- `exls_matrix/middle_de_research_notes.md`

These documents are mandatory, not optional background.

## Team Composition

All engineering roles in this team are senior-level.

- Data Engineer
- DevOps Engineer
- DataOps Engineer
- DBA
- SQL Engineer
- ELT or ETL Engineer
- Scala or Python or Spark Engineer
- Hadoop Engineer
- Reviewer
- Technical Writer
- Arbiter
- Registry Steward (ledger and traceability owner)

## Role Responsibilities

### Data Engineer

Define competencies for data model and pipeline design:
- data modeling, mart design, and semantic consistency
- batch and incremental processing patterns
- data quality controls and reliability patterns
- scalability and cost-awareness in data architecture

### DevOps Engineer

Define platform and delivery competencies:
- CI/CD reliability and deployment safety
- infrastructure as code and environment parity
- observability, alerting, and rollback readiness
- secrets management and operational resilience

### DataOps Engineer

Define operational data lifecycle competencies:
- orchestration and dependency management
- data quality operations and incident response
- SLA and SLO control for data pipelines
- workflow governance and release discipline

### DBA

Define database governance and performance competencies:
- physical design and indexing strategy
- query-plan literacy and workload management
- backup/recovery and durability patterns
- access controls, compliance, and change safety

### SQL Engineer

Define SQL craft competencies:
- readable and maintainable SQL design
- correctness, edge-case handling, and reproducibility
- optimization and anti-pattern avoidance
- technical documentation for SQL logic

### ELT or ETL Engineer

Define transformation and movement competencies:
- source-to-target mapping quality
- robust extraction and load design
- change-data handling and idempotency
- reconciliation and recoverability

### Scala or Python or Spark Engineer

Define distributed compute competencies:
- code quality and maintainability standards
- Spark execution tuning and resource efficiency
- failure handling and retry discipline
- testability and packaging for production execution

### Hadoop Engineer

Define Hadoop ecosystem competencies:
- HDFS and storage strategy
- YARN and cluster resource governance
- distributed job stability and performance triage
- platform-level operational troubleshooting

### Reviewer

Validate solution quality against request context:
- verify matrix structure matches task goal
- check consistency across competency domains
- identify blind spots, overlap, and missing criteria
- assess readiness for attestation usage

### Technical Writer

Convert technical discussion into human-readable technical language:
- produce precise and unambiguous competency statements
- normalize terminology and rubric wording
- structure output for practical evaluation usage
- keep language concise, technical, and actionable

### Arbiter

Drive disputes to final consensus:
- resolve conflicts between role proposals
- issue final binding decisions with rationale
- ensure no blocking disagreement remains
- confirm final matrix is internally coherent

### Registry Steward

Own dialog-scoped memory and change traceability:
- initialize and maintain `Q-*`, `CL-*`, and `EV-*`
- enforce links `Q-* -> CL-* -> EV-*`
- track key deltas and affected artifacts
- track branch states (`active`, `in_progress`, `merged`, `dead`)
- keep output token-efficient through ID reuse and delta-first updates

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
- connect each evolution item to relevant `CL-*` and `Q-*`
- set evolution domain on each item: `sql`, `b2c`, or `cross-domain`
- store delta summary, changed artifacts, and key technical points
- track branch state per affected workstream: `active`, `in_progress`, `merged`, `dead`
- for `dead` branches, record closure reason and replacement branch/path
- for `in_progress` branches, record open risks and next checkpoint

## Collaboration Protocol

1. Each role submits findings with severity (`critical`, `major`, `minor`, `note`).
2. Team discusses competency boundaries, overlap, and conflicts.
3. Registry Steward initializes and/or updates `Q-*`, `CL-*`, `EV-*` and links.
4. Reviewer validates alignment with attestation-matrix objective.
5. Technical Writer rewrites agreed technical points into human-readable technical format.
6. Arbiter resolves unresolved conflicts and confirms final consensus.
7. Return one consolidated result with clear next actions.

## Output Format

Return sections in this order:
1. `Selected Team: de-matrix-команда`
2. `Context Reuse` (reused IDs, updated IDs, challenged/confirmed IDs)
3. `Ledger Traceability` (`Q-*` to `CL-*` to `EV-*`)
4. `Evolution Snapshot` (`EV-*`, linked `Q-*`, linked `CL-*`, branch states, key deltas)
5. `Role Findings` (delta-focused by role)
6. `Competency Matrix Draft` (attestation-ready structure)
7. `Disputes and Decisions` (arbiter resolutions)
8. `Technical Writer Output` (human-readable technical version)
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
- linked_questions: <Q-ids or none>
- linked_conclusions: <CL-ids or none>
- domain: <sql|b2c|cross-domain>
- scope: <files/components/pipeline scope>
- delta: <what changed since previous state>
- key_points: <1-3 key technical points>
- branch_state: <active|in_progress|merged|dead>
- branch_note: <status or closure reason>
- regression_focus: <areas that require regression checks>
```

## Competency Matrix Mini Template (mandatory)

Use this compact structure:

```markdown
### Competency Matrix Draft
- scope: <team/project scope for attestation>
- roles_covered: <list of roles>
- rubric_scale: <for example 0-3 or 0-5 with definitions>
- competency_domains:
  - <domain>: <senior expectations and evidence>
  - <domain>: <senior expectations and evidence>
- cross_domain_requirements: <architecture, reliability, governance, communication, ownership>
- assessment_artifacts: <code samples, runbooks, incidents, docs, delivery outcomes>
- evaluation_rules: <how scores are assigned and validated>
- open_gaps: <missing criteria or evidence>
```
