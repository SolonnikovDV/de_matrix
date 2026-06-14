---
name: presentation-team
description: Builds and validates technical presentations with generated visuals, diagrams, test layout, and style consistency using a cross-functional expert team. Use when user requests presentation-команда, презентация-команда, slide deck design, architecture storytelling, or business value presentation.
disable-model-invocation: true
---

# Presentation Team Workflow

## Trigger

Use this skill when the user explicitly selects `presentation-команда` or equivalent alias from the routing rule.

## Team Composition (Permanent Roster)

**All roles below are mandatory from session start.** Every role must contribute before deck delivery. Do not skip, defer, or silently omit roles unless the user explicitly requests a reduced team.

- Business Owner
- Technical User (primary end-user representative)
- Copywriter
- Designer (дизайнер)
- Layout Designer (верстальщик)
- SQL Engineer
- Data Engineer
- DevOps Engineer
- UI/UX Designer
- Architect
- Technical Writer
- Reviewer
- Censor
- Language and Context Checker
- Presentation Developer
- Diagram and Infographic Specialist
- Arbiter
- Registry Steward (ledger and traceability owner)

## Role Responsibilities

### Business Owner

Validate business and sales narrative:
- ROI framing, budget impact, and decision criteria for adoption
- alignment of value proposition with buyer priorities (risk, cost, speed)
- pilot success metrics and go/no-go gates for scaling

### Technical User

Represent primary end-user perspective (e.g. data engineer):
- validate day-to-day workflows, pain points, and tool fit
- confirm terminology, scenarios, and realistic usage examples
- flag missing technical prerequisites or adoption blockers

### Copywriter

Own message clarity and persuasion:
- remove filler, repetition, and vague claims
- sharpen headlines, benefit statements, and call-to-action
- ensure consistent tone for mixed business + technical audience

### Designer (дизайнер)

Own visual identity and art direction:
- define palette, gradients, accent usage, and bigtech / casual tone
- direct cover art concept (split layout, SVG semantics, glow, status colors)
- approve or reject aesthetic shifts (e.g. strict corporate vs vibrant engineering)
- align infographic color language with product semantics (INFO/WARN/ALERT, trade-offs)
- hand off tokens and visual brief to Layout Designer and Presentation Developer

### Layout Designer (верстальщик)

Own slide composition and print/export quality:
- balance whitespace and content density per slide (75–90% fill target)
- enforce typography scale, grid alignment, and visual hierarchy
- optimize layout for projection, PDF export, and readability at distance
- enforce **bigtech dev** visual tone by default; reject over-strict corporate dull palettes unless user asks
- apply **title-only cover** rule for Mode B framework decks

### SQL Engineer

Validate data and SQL claims in slides:
- correctness of SQL logic and metrics interpretation
- consistency of SQL-driven examples and caveats
- technical accuracy of query and data model explanations

### Data Engineer

Validate data pipeline and transformation narrative:
- correctness of data flow explanations
- alignment of platform constraints with proposed architecture
- scalability and reliability statements in the deck

### DevOps Engineer

Validate delivery and operations content:
- container and deployment model correctness
- CI/CD and release gate representation
- observability and rollback readiness claims

### UI/UX Designer

Own visual clarity and usability:
- slide hierarchy, spacing, readability, and information density
- visual consistency of color, typography, and component style
- audience-centered content structure and comprehension flow

### Architect

Own technical coherence:
- consistency of architectural decisions across slides
- correctness of component interactions and boundaries
- trade-off clarity and dependency mapping

### Technical Writer

Convert team output into clear technical language:
- rewrite content in concise, precise, and readable form
- normalize terminology and remove ambiguity
- ensure consistent narrative from problem to outcome

### Reviewer

Perform independent quality validation:
- verify presentation completeness against request context
- check internal consistency across technical and business sections
- issue verdict on readiness (`pass`, `pass_with_risk`, `fail`)

### Censor

Filter problematic content:
- remove unsupported claims and risky wording
- enforce compliance with approved communication boundaries
- ensure no misleading or sensitive phrasing remains

### Language and Context Checker

Validate language quality:
- orthography, grammar, punctuation, and stylistic consistency
- semantic integrity and contextual correctness
- alignment of terminology across slides and speaker notes

### Presentation Developer

Own deck assembly and style implementation:
- build slide structure and maintain style system
- ensure template consistency, component reuse, and layout quality
- prepare export-ready final package

### Diagram and Infographic Specialist

Own visual models:
- generate architecture diagrams, process flows, and infographics
- maintain visual accuracy and readability
- ensure diagrams match technical facts and narrative goals

### Arbiter

Resolve disputes and finalize consensus:
- mediate conflicts across specialist recommendations
- produce final binding decisions with rationale
- confirm final deck readiness and acceptance criteria coverage

### Registry Steward

Own dialog-scoped memory and traceability:
- initialize and maintain `Q-*`, `CL-*`, `EV-*`
- enforce links `Q-* -> CL-* -> EV-*`
- track deltas, artifacts, and branch states
- keep answers token-efficient through ID reuse and delta-focused updates
- run **dialog context intake** before brief: user constraints, revision deltas, repo doc list

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
- set evolution domain: `presentation` by default, `cross-domain` when needed
- store delta summary, changed artifacts, and key technical points
- track branch state: `active`, `in_progress`, `merged`, `dead`
- for `dead` branches, record closure reason and replacement
- for `in_progress` branches, record blockers and next checkpoint

## Collaboration Protocol

1. **Registry Steward** opens intake: dialog constraints, `Q-*`/`CL-*`, repo doc scan list.
2. Business owner and technical user frame audience goals, deck mode (A/B/C), and decision criteria.
3. **Designer** sets visual tone, palette tokens, and cover/infographic art direction.
4. Technical Writer + domain roles (SQL, DE, DevOps, Architect) aggregate facts into **Brief v0.x**; user confirms before build.
5. Copywriter drafts concise storyline; layout designer proposes slide density and grid from designer brief.
6. Diagram and infographic specialist assigns primary visual per slide (infographic matrix).
7. Each role submits findings with severity (`critical`, `major`, `minor`, `note`) — **all roles required**.
8. Presentation developer assembles `deck.html` from slide map + content blocks + designer style tokens.
9. UI/UX designer validates hierarchy and comprehension; designer validates visual identity match.
10. Reviewer validates completeness against brief and dialog deltas.
11. Censor and language-context checker run content quality checks (including `е` vs `ё` policy when specified).
12. Registry Steward updates `Q-*`, `CL-*`, `EV-*` and links.
13. Arbiter resolves unresolved disputes and confirms final consensus.
14. Export PDF; on user revision, log delta in `EV-*` and re-run affected roles only.
15. Return one consolidated result and next actions.

## Presentation Composition Methodology (Mandatory)

Follow this methodology for every new or revised deck unless the user explicitly overrides.

### Deck modes (choose in brief)

| Mode | When | Primary audience | Pilot slide |
|------|------|------------------|-------------|
| **A · Sales / adoption** | продукт, внедрение, ROI, buyer decision | DE + management + product + business | yes (default) |
| **B · Framework / standard** | корпоративный стандарт, архитектура, паттерны, governance | DE · DA · DQ · business · architects | **no** (unless user asks) |
| **C · Hybrid** | явный запрос смешать ценность и глубину | по брифу | по брифу |

Do not default to Mode A when user positions the subject as **стандарт**, **фреймворк**, **reference implementation**, or asks to drop pilot/sales blocks.

Reference implementation in this repo: Mode B → `docs/presentation/deck.html` (фреймворк DQ-b2c).

---

### Dialog context intake (Registry Steward + Technical Writer)

Aggregate material **from the current dialog first**, then from the repo. Never invent facts missing from both.

**Sources (priority order):**
1. **Explicit user constraints** in the dialog — product name, audience, forbidden blocks (e.g. «без pilot», «титул только заголовок»), tone, language policy (`е`/`ё`).
2. **Confirmed brief versions** — treat user approval of brief v0.x as binding scope; link to `CL-*`.
3. **Revision deltas** — each user message after v1 is a delta spec; map to slide numbers or slide titles, not vague «сделай лучше».
4. **Ledgers** — reuse `Q-*`, `CL-*`, `EV-*` instead of re-deriving; cite IDs in internal planning.
5. **Repository docs** — authoritative `.md` under product scope (e.g. `dq/docs/DQ_FACTORY_FRAMEWORK.md`, architecture/playbook/testing docs).
6. **Code artifacts** — function names, table names, YAML paths when slides claim implementation facts.
7. **Contacts** — git config, README, team metadata; **never** fabricate email/phone; use placeholder until user provides.

**Intake checklist (before slide map):**
- [ ] Product name and one-line positioning
- [ ] Audience roles (who must recognize themselves on slides)
- [ ] Deck mode (A / B / C)
- [ ] In-scope / out-of-scope (pilot, sales, doc inventory, repo links on contacts)
- [ ] Title rule: title-only vs title + hero content
- [ ] Visual tone: bigtech dev (default) vs strict corporate — confirm after first draft if ambiguous
- [ ] Language policy and forbidden meta-phrases
- [ ] Export target path and filename

**Brief gate:** publish `Presentation Brief v0.x` and wait for user confirmation (or explicit «собирай») before building `deck.html`. On revision-only requests, skip full brief but document delta in `EV-*`.

---

### Information aggregation pipeline

```text
Dialog + repo intake
    → Brief v0.x (scope, mode, audience, anti-goals)
    → User confirm / delta
    → Slide map (numbered, one purpose per slide)
    → Per-slide content blocks (lead, bullets, tables, code, claims)
    → Infographic assignment (matrix below)
    → HTML assembly + style tokens
    → Role QA (Layout, Diagram, Copywriter, Censor)
    → PDF export
    → User feedback → delta EV → re-export
```

**Per-slide content block schema** (planning unit before HTML):

| Field | Rule |
|-------|------|
| `purpose` | one sentence — why this slide exists |
| `headline` | declarative Russian; no meta («без дублирования», «честно») |
| `lead` | optional 1–2 lines under title |
| `primary_visual` | diagram / cycle / grid / table / cover-art — required on text-heavy slides |
| `evidence` | doc path, dialog `CL-*`, or code reference |
| `roles_hook` | which audience segment this slide serves |

**Aggregation rules:**
- One message → one primary idea per slide; merge duplicates across slides (Copywriter).
- Prefer **named artifacts** from docs (tables, functions, statuses INFO/WARN/ALERT) over generic claims.
- Closing slide: **application scope + outcome**, not documentation bibliography (unless user requests catalog).
- Contacts slide: person, role, team, **topics to ask about**; omit repo/docs unless user asks.

---

### Standard slide maps (adapt to product)

#### Mode A · Sales / adoption (~11 slides)

| # | Slide | Content |
|---|-------|---------|
| 1 | Title | Value prop, pills, ≤3 hero points |
| 2 | Problem | Pipeline + iceberg + pain cards |
| 3 | Cost / economics | Before/after + TCO (single economics slide) |
| 4 | Solution | Feature grid + one time-to-value metric |
| 5 | Roles | 2×2 role cards + scenario bar |
| 6 | How it works | Architecture + funnel + tech requirements |
| 7 | Demo | One screenshot + callouts |
| 8 | Positioning | Comparison table + decision grid + scenario bar |
| 9 | Roadmap + limits | Timeline + covered vs limits + scenario bar |
| 10 | Pilot + KPI | Table + steps + metrics + scenario bar by role |
| 11 | CTA | Contact only — no summary repeat |

Remove by default: summary slide repeating title, mini-demo + full demo, split strength/weakness slides, second economics slide.

#### Mode B · Framework / standard (~12 slides, DQ-b2c pattern)

| # | Slide | Content |
|---|-------|---------|
| 1 | **Title only** | Product name typography only — **no** pills, hero points, audience tags |
| 2 | Overview | Lead, tag-row (stack + audience), 3× feature-card grid |
| 3 | Why standard | Callout (essence) + method-cycle (4 steps) + layer-stack (3 layers) + compare-box |
| 4 | Architecture | arch-flow + component table + ETL integration + code snippet |
| 5 | Pattern catalog | Pattern table or grid with use cases |
| 6 | Interface + registration | Contract, mapping, controller registration flow |
| 7 | Design rationale | pillar-bars or decision pillars — why this architecture |
| 8 | Trade-offs | decision-grid with plus/minus columns (honest limits) |
| 9 | Scale + resilience | change matrix (what changes → which artifact) |
| 10 | Governance + business value | roles-grid + stat cells or outcome bar |
| 11 | Application scope + closing | when to use / when not — **no doc file list** |
| 12 | Contacts | Developer name, role, team, topic list — **no repo/docs** unless requested |

**Title split rule (Mode B):** if overview content would land on slide 1, **move it to slide 2**; keep slide 1 as visual cover only.

---

### Slide filling patterns (HTML components)

Reuse these compositional patterns from `docs/presentation/deck.html`:

| Pattern | CSS / structure | Use when |
|---------|-----------------|----------|
| Cover split | `.slide-cover`, `.cover-left`, `.cover-right`, `.cover-art`, `.cover-glow`, `.cover-rule` | Title-only slide 1 |
| Overview | `.lead` + `.tag-row` + `.feature-grid` / `.feature-card` | Product essence, audience, 3 pillars |
| Methodology | `.callout` + `.method-cycle` / `.method-step` + `.layer-stack` / `.layer-item` | Standard / process / layers |
| Architecture | `.arch-flow`, `.arch-box`, `.arch-arrow` + `table.data` | Execution chain, responsibilities |
| Code fact | `.code-block` | One real invocation or signature |
| Patterns | `table.data` with pattern names | Catalog slides |
| Rationale | `.pillar-grid`, `.pillar` | Design principles (5 pillars max) |
| Trade-offs | `.decision-grid`, `.decision-col.plus`, `.decision-col.minus` | Benefits vs limits on one slide |
| Scale | `.change-matrix`, `.change-cell` | What to change when scaling |
| Governance | `.roles-grid`, `.stat-grid` | Roles + business outcomes |
| Closing | `.apply-grid`, `.closing-bar` | Scope matrix + one-line outcome |
| Contacts | `.contact-card`, `.topic-list`, `.topic-item`, `.topic-num` | Developer reach-out |

**Density:** target **75–90%** meaningful fill; use asymmetric columns (`cols-60-40`, `cols-55-45`, `cols-2`) before adding slides.

---

### Infographic assignment matrix

Every **text-heavy** slide must have a **primary visual** (not only bullets).

| Slide intent | Preferred visual | Secondary |
|--------------|------------------|-----------|
| Title | Cover SVG (pipeline → factory → layers; status dots INFO/WARN/ALERT) | gradient + glow |
| Overview | 3× feature-card with stroke icons | tag-row pills |
| Why standard | method-cycle (numbered steps) | layer-stack + compare-box |
| Architecture | arch-flow diagram | component table |
| Patterns | table + status colors | icon per pattern type |
| Registration | flow or sequence boxes | mapping table |
| Rationale | pillar-bars | — |
| Trade-offs | balance / plus-minus columns | icon check/x |
| Scale | change matrix | reuse nodes |
| Governance | roles-grid | stat cells |
| Application | 2-column apply / not apply | closing bar |
| Contacts | topic numbered list | optional mini flow «question → doc → deploy» |

**Diagram and Infographic Specialist** validates: labels match doc facts; no decorative-only graphics without semantic anchors.

---

### Visual system and design tone

**Designer (дизайнер)** owns palette and art direction; **Layout Designer** applies grid and density; **Presentation Developer** implements CSS tokens.

**Default tone: bigtech product engineering** — clean, confident, slightly casual; **not** bank-grade ultra-strict minimalism unless user asks.

**Palette tokens (reference — adjust per product, keep relationships):**

| Token | Example | Usage |
|-------|---------|--------|
| `--accent` | `#0d5cab` | headers, links, badges |
| `--accent-cyan` | `#4db8ff` | cover emphasis, glow, highlights |
| `--accent-soft` | `#e8f1fb` | table headers, tags, cards |
| `--navy` | `#0d3d6b` | cover gradient base |
| `--ok` / `--warn` / `--alert` | green / amber / red | INFO/WARN/ALERT, trade-offs |
| `--radius` | `8px` | cards, pills — soft bigtech, not sharp corporate |

**Cover (Mode B):**
- Split layout ~58% / 42%; left = title only + `.cover-rule`
- Right = `.cover-glow` + semantic SVG (pipeline, factory block, stacked layers, shield, status dots)
- Gradient: `135deg` navy → accent → accent-bright

**Icons:** stroke SVG sprite in hidden `<svg>` + `<use href="#i-*">` — **never emoji**.

**Typography:** body ≥10pt; card headings 10.5–11pt; slide title ~21pt; cover title ~44pt; footer 7.5–8pt service text only.

**Layout components:** `roles-grid`, `scenario-bar`, `decision-grid`, `feature-grid`, `method-cycle`, `layer-stack`, `arch-flow`, `change-matrix`, `cols-60-40`, `cols-55-45`.

**Slide chrome:** top gradient bar on content slides; `.slide-badge` pill with slide index; footer `product · year` (omit raw repo paths unless user wants).

**Design anti-patterns (Layout Designer rejects):**
- Flat navy-only palette with no accent-soft fills — reads as «too strict / dull»
- Title slide overloaded with pills, hero metrics, audience tags (Mode B)
- Gray boxes without left accent or icon anchor
- Replacing semantic cover art with abstract grid-only decoration
- Fake percentage meters without pilot data

---

### Core principles

1. **Audience-first framing** — mixed audience: pick mode A or B explicitly; hooks for each role on dedicated slides.
2. **Fewer slides, no duplication** — merge overlapping content; each message once.
3. **No water** — no meta phrases in titles (e.g. «честно», «без пересечения с другими слайдами»).
4. **Honest positioning** — strengths and weaknesses together when comparing alternatives or architecture choices.
5. **Evidence over fake metrics** — qualitative before/after or pilot placeholders marked with `*`.
6. **Densify sparse slides** — use 2×2 grids, scenario bars, expanded tables; target 75–90% fill.
7. **Dialog fidelity** — user corrections in the same session override earlier brief defaults (supersede `CL-*`, log `EV-*`).

### Language (Russian decks)

- Russian primary; keep common EN terms where standard: lineage, impact, pilot, open source, CR, KPI, ROI, factory, adapter, playbook.
- Use **`е` instead of `ё`** when user or project policy specifies.
- Correct Russian terms only (e.g. **инцидент**, not `incident` / `инцident`).
- Headlines: short, declarative, no editorial asides.

### Mandatory review dimensions (Reviewer QA gate)

Before verdict `pass`:
- visual identity and palette match designer brief (Designer)
- fill density per slide (Layout Designer)
- font size for projection (Layout Designer + UI/UX)
- content placement and grid (Layout Designer)
- infographic accuracy (Diagram Specialist)
- duplication scan across deck (Copywriter)
- audience hooks match brief mode (Business Owner + Technical User)
- pilot slide present only when Mode A or user requested (Business Owner)
- title-only rule respected in Mode B (Layout Designer)
- contacts: no fabricated email; no repo/docs unless requested (Censor)
- visual tone: not over-strict corporate without user ask (UI/UX + Layout Designer)
- unsupported claims removed (Censor)

Verdicts: `pass`, `pass_with_risk`, `fail`.

### Delivery artifacts

- HTML source deck (print-oriented CSS, A4 landscape) — default `docs/presentation/deck.html`
- PDF export via `docs/presentation/export-pdf.sh` or Chrome headless
- Output PDF name aligned with product (e.g. `DQ-b2c-framework-deck.pdf`)
- Optional one-pager for leave-behind

### Anti-patterns (reject in review)

- Emoji or messenger-style pictograms
- Fake percentage meters without real pilot data
- Repeating hero metrics on summary slide
- Meta commentary in titles
- Documentation file list on closing slide (Mode B default)
- Repo paths on contacts slide when user removed them
- 15+ slides with the same «0 ₽ / pilot / инцидент» blocks (Mode A bloat)

Project-specific rule file (when present): `.cursor/rules/presentation-team-methodology.mdc`

## Output Format

Return sections in this order:
1. `Selected Team: presentation-команда`
2. `Context Reuse` (reused IDs, updated IDs, challenged/confirmed IDs)
3. `Ledger Traceability` (`Q-*` to `CL-*` to `EV-*`)
4. `Evolution Snapshot` (`EV-*`, linked `Q-*`, linked `CL-*`, branch states, key deltas)
5. `Presentation Plan` (audience, goals, storyline, slide map)
6. `Technical Validation` (engineer findings by domain)
7. `Visual Package` (diagrams, infographics, style and layout checks)
8. `Language and Censorship Checks` (orthography, context, compliance)
9. `Reviewer Verdict`
10. `Disputes and Decisions` (arbiter resolutions)
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
- domain: <presentation|cross-domain>
- scope: <slides/diagrams/content/assets scope>
- delta: <what changed since previous state>
- key_points: <1-3 key technical points>
- branch_state: <active|in_progress|merged|dead>
- branch_note: <status, blockers, or closure reason>
- regression_focus: <areas requiring consistency re-check>
```
