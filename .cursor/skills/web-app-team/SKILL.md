---
name: web-app-team
description: Runs a full-cycle web application delivery team for web ui plus backend with docker or kubernetes runtime, ci cd gates, testing, security, monitoring, scaling, ai integration only when justified, and documentation. Use when user requests web-app-команда or full SDLC web app delivery.
disable-model-invocation: true
---

# Web App Team Workflow

## Trigger

Use this skill when the user explicitly selects `web-app-команда` or equivalent alias from the routing rule.

## Team Composition

All engineering roles in this team are senior-level.

- Product or System Analyst
- Solution Architect
- Frontend Engineer (Web UI)
- Backend Engineer
- DevOps or Platform Engineer (Docker, Kubernetes)
- CI/CD and Release Engineer
- QA or Test Engineer
- Security Engineer (AppSec or DevSecOps)
- SRE or Observability Engineer
- AI Integration Engineer (only when AI is justified)
- Best Practices Scout
- Technical Writer
- Reviewer
- Critic
- Arbiter
- Registry Steward (ledger and traceability owner)

## Role Responsibilities

### Product or System Analyst

Owns requirement quality and traceability:
- model business workflows and system boundaries
- define acceptance criteria and non-functional requirements
- ensure requirement-to-test traceability

### Solution Architect

Owns architecture and design decisions:
- define system architecture and integration patterns
- resolve trade-offs across cost, complexity, and resilience
- maintain architecture decision records

### Frontend Engineer

Owns web ui delivery:
- component architecture, state, and UX behavior
- accessibility, performance budgets, and browser reliability
- frontend testing strategy for critical flows

### Backend Engineer

Owns service and API delivery:
- domain logic, API contracts, and integration reliability
- data consistency and failure handling
- backend performance and maintainability

### DevOps or Platform Engineer

Owns runtime and infrastructure:
- containerization standards (Docker)
- Kubernetes deployment topology and runtime health
- environment parity and operational reliability

### CI/CD and Release Engineer

Owns delivery gates and release safety:
- pipeline stages and policy gates
- artifact quality checks and rollback readiness
- deployment controls and release automation

### QA or Test Engineer

Owns testing strategy and quality gates:
- test pyramid coverage across unit, integration, and e2e
- regression strategy and defect quality
- release quality verdict and blocking criteria

### Security Engineer

Owns security posture:
- threat modeling and security controls
- pipeline security scans and dependency hygiene
- secret handling and hardening controls

### SRE or Observability Engineer

Owns reliability and production feedback:
- logging, metrics, tracing, and alerting coverage
- SLI/SLO setup and incident response readiness
- scaling and capacity risk visibility

### AI Integration Engineer

Owns justified AI usage only:
- validate if AI is needed or deterministic logic is sufficient
- define model guardrails, fallback paths, and failure policy
- control quality, risk, and cost for AI-enabled features

### Best Practices Scout

Continuously scans and applies relevant engineering best practices:
- monitor practical best practices for the current solution context
- propose high-value updates to architecture, coding, delivery, and operations
- reject hype-driven changes without practical impact

### Technical Writer

Converts engineering outcomes into clear technical documentation:
- write implementation-facing docs and runbooks
- normalize terminology and reduce ambiguity
- ensure docs stay aligned with delivered behavior

### Reviewer

Performs independent alignment and quality validation:
- evaluate whether result fits original task context
- verify completeness of architecture-to-delivery chain
- issue review verdict with explicit risks

### Critic

Challenges assumptions and hidden risks:
- stress-test design choices and weak assumptions
- identify blind spots, edge risks, and failure modes
- propose alternatives when risk profile is unacceptable

### Arbiter

Resolves disputes and finalizes consensus:
- settle conflicts across roles with rationale
- ensure unresolved blockers are either fixed or explicitly accepted
- confirm final decision set is coherent and actionable

### Registry Steward

Owns dialog-scoped memory and traceability:
- initialize and maintain `Q-*`, `CL-*`, and `EV-*`
- enforce links `Q-* -> CL-* -> EV-*`
- track deltas, artifacts, branch states, and decision lineage
- keep responses token-efficient through ID reuse and delta-first updates

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
- set evolution domain: `web-app` by default, `cross-domain` when needed
- store delta summary, changed artifacts, and key technical points
- track branch state: `active`, `in_progress`, `merged`, `dead`
- for `dead` branches, record closure reason and replacement
- for `in_progress` branches, record blockers and next checkpoint

## Collaboration Protocol

1. Each role submits findings with severity (`critical`, `major`, `minor`, `note`).
2. Reviewer validates context alignment and scope completeness.
3. Critic challenges assumptions and highlights latent risks.
4. Team resolves design, delivery, and risk conflicts.
5. Registry Steward initializes and/or updates `Q-*`, `CL-*`, `EV-*` and links.
6. Technical Writer transforms consensus into clear technical documentation.
7. Arbiter resolves unresolved disputes and confirms final consensus.
8. Return one consolidated result with next actions.

## Delivery Gates (mandatory)

- Architecture Gate: architect + reviewer + critic + arbiter
- Security Gate: security engineer + reviewer
- Quality Gate: qa or test engineer + reviewer + critic
- Release Gate: devops or ci-cd engineer + sre + arbiter

If any gate is `fail`, release recommendation is `no_go` until resolved or explicitly accepted by arbiter.

## Output Format

Return sections in this order:
1. `Selected Team: web-app-команда`
2. `Context Reuse` (reused IDs, updated IDs, challenged/confirmed IDs)
3. `Ledger Traceability` (`Q-*` to `CL-*` to `EV-*`)
4. `Evolution Snapshot` (`EV-*`, linked `Q-*`, linked `CL-*`, branch states, key deltas)
5. `Role Findings` (delta-focused by role)
6. `Delivery Gates` (architecture, security, quality, release)
7. `Reviewer Verdict`
8. `Critic Notes`
9. `Disputes and Decisions` (arbiter resolutions)
10. `Technical Writer Output`
11. `Final Consensus`
12. `Action Plan` (ordered, concrete steps)

## Context Reuse Mini Template (mandatory when overlap exists)

```markdown
### Context Reuse
- reused: <CL-ids or none>
- updated: <CL-id -> new status/reason, or none>
- challenged: <CL-ids + outcome, or none>
- confirmed: <CL-ids + evidence, or none>
- superseded: <old CL-id -> new CL-id, or none>
```

## Ledger Traceability Mini Template (mandatory)

```markdown
### Ledger Traceability
- dialog_scope: <current-dialog-window>
- questions: <Q-ids touched in this response>
- links: <Q-id -> CL-id(s) -> EV-id(s)>
- new_ids: <new Q/CL/EV ids or none>
- remapped_ids: <old id -> new id, if superseded>
```

## Evolution Mini Template (mandatory when change history matters)

```markdown
### Evolution Snapshot
- ev_id: <EV-id>
- linked_questions: <Q-ids or none>
- linked_conclusions: <CL-ids or none>
- domain: <web-app|cross-domain>
- scope: <services/ui/pipelines/infra scope>
- delta: <what changed since previous state>
- key_points: <1-3 key technical points>
- branch_state: <active|in_progress|merged|dead>
- branch_note: <status, blockers, or closure reason>
- regression_focus: <areas requiring regression checks>
```
