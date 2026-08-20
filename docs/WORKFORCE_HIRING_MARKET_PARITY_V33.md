# EAY Workforce + Hiring — Market Parity & Category Leadership V33

## Product doctrine

Market leaders define the **starting line**, not the destination.

EAY will study the problem-solving patterns and meaningful capabilities proven by
leading workforce-management and frontline-hiring products, implement equivalent
business outcomes where they fit our operating model, and then extend them with
EAY operational intelligence. We do not copy proprietary UI, text, code or
protected workflows.

The execution ladder is:

`Market Leader Baseline -> EAY Parity -> EAY Intelligence -> Governed Autonomy -> Verified Outcome`

A capability is not "done" because a mock, endpoint or synthetic test exists.
Repository evidence, field evidence and production evidence remain separate.

## Canonical architecture boundary

Workforce and Hiring are one lifecycle and share one Employee Master:

`TC digest/encrypted value -> employee_id -> roster_ids -> warehouse scope -> employment dates`

Hiring:

`Norm -> HR Actual -> committed HC -> vacancy -> candidate -> evidence -> decision -> hire -> Employee Master -> first shift -> retention/outcome`

Workforce:

`Demand -> workload -> skills -> policy -> optimizer proposal -> approved roster -> attendance -> outcome -> learning`

Optimizer/recommendation output is never direct roster or attendance authority.
Unknown tenant, scope, identity, policy or evidence fails closed.

## Market-leader baseline matrix

Status legend:

- `IMPLEMENTED` — product capability exists in the canonical branch with code/tests.
- `PARTIAL` — meaningful foundation exists but the end-user or authority lifecycle is incomplete.
- `GAP` — required parity capability is not yet implemented.
- `FIELD BLOCKED` — software exists but real device/customer/production acceptance is missing.

### Workforce Management

| Capability | Market baseline | EAY current | EAY advantage target |
|---|---|---|---|
| Demand forecasting | Granular demand by time/location | PARTIAL | Orders + basket + picking + inbound + putaway + cycle count + local-event/weather signals |
| Labor requirement | Demand converted to role/skill demand | IMPLEMENTED foundation | Task/role-specific workload and effective-capacity authority |
| Auto scheduling | Skills, availability, rules, cost | PARTIAL | Operational KPI impact and explainable proposal ranking |
| Availability/preferences | Employee availability and preferred hours | GAP | Feed preference/fairness into optimizer without weakening hard rules |
| Open shifts | Employees claim eligible open shifts | GAP | Eligibility ranked by fatigue, skill, productivity and expected KPI impact |
| Shift swaps | Governed employee-to-employee swaps | GAP | Pre-approved swap suggestions with rest/compliance/capacity proof |
| Skills/certifications | Skill-aware assignment | IMPLEMENTED foundation | Academy certification + task proficiency + observed productivity |
| Fatigue/compliance | Rest/overtime/working-rule controls | IMPLEMENTED foundation | Temporal policy versioning and explainable override evidence |
| Intraday staffing | Required vs scheduled vs actual | PARTIAL | Demand variance -> staffing action -> predicted KPI effect |
| Mobile self-service | Shift/leave/availability actions | PARTIAL | One Employee Master + governed device presence + operational context |
| Schedule fairness | Fair distribution / preferences | GAP | Auditable fairness score with protected-attribute-safe inputs |
| Scenario planning | What-if labor/cost scenarios | IMPLEMENTED foundation | Demand, budget and service-risk outcomes in one scenario |
| Manager override learning | Learn from planner edits | IMPLEMENTED foundation | Measure override outcome and promote only proven policy/model changes |
| Attendance presence | Shift-bound trusted check-in/out | IMPLEMENTED / FIELD BLOCKED | Device attestation + GPS + roster identity + signed presence proof |
| Exit revocation | Remove future access and shifts | IMPLEMENTED / FIELD BLOCKED | Employee lifecycle -> roster/device/OIDC revocation chain |

### Hiring / Frontline Talent Acquisition

| Capability | Market baseline | EAY current | EAY advantage target |
|---|---|---|---|
| Headcount plan vs actual | Norm/plan compared with actual HC/FTE | IMPLEMENTED foundation | HR Actual + Employee Master reconciliation + source SHA/freshness |
| Committed HC | Future starts/exits included | IMPLEMENTED foundation | 30/60/90 committed-HC and uncovered-gap projection |
| Demand-driven requisition | Hiring need derived from workforce demand | PARTIAL | Forecast workload + attrition + committed HC creates explainable need signal |
| Vacancy approval | Governed requisition approval | IMPLEMENTED | Norm/actual/current commitments shown at decision time |
| Candidate pipeline | Candidate lifecycle and states | IMPLEMENTED foundation | Vacancy evidence + quality-of-hire outcome loop |
| Candidate evidence | Secure candidate documents/evidence | IMPLEMENTED foundation | Private object authority, malware/MIME gates and retention evidence |
| Candidate decision | Human-controlled approve/reject | IMPLEMENTED | Decision trace tied to vacancy and future outcome |
| Mobile/QR apply | Low-friction frontline application | GAP | Depot/shift eligibility and nearest-fit routing |
| Conversational screening | Automated pre-screening | GAP | Policy-grounded screening with human decision boundary |
| Interview self-scheduling | Candidate books eligible slots | GAP | Interview capacity + depot manager availability + SLA optimization |
| Candidate nudges | Automated reminders/comms | PARTIAL | Multi-channel adapter with idempotent outbox and response state |
| Offer lifecycle | Offer creation/acceptance | GAP | Offer -> Employee Master provisional identity -> onboarding gate |
| Onboarding | Documents/tasks before Day One | PARTIAL | Academy + device/roster readiness + first shift as one activation bundle |
| Hire activation | Hire creates employee authority | IMPLEMENTED | Canonical TC/employee/roster identity and conflict fail-closed |
| First shift | Day-One schedule created | IMPLEMENTED | Vacancy-to-first-shift transactional lifecycle |
| No-show handling | Detect and recover Day-One no-show | GAP | Auto reopen uncovered capacity without duplicating headcount |
| Source attribution | Track source/referral/partner | IMPLEMENTED foundation | Cost + retention + productivity by source |
| Time-to-hire funnel | Stage SLA analytics | GAP | Need-to-Day-One SLA, not ATS-only application SLA |
| Quality of hire | Post-hire outcome | GAP | Day 7/30/90 retention + attendance + productivity + quality |
| Internal mobility | Existing employee movement | GAP | Skill/certification + commute + capacity + retention-aware movement |

## V33 staffing authority

Hiring staffing decisions must display distinct quantities instead of collapsing
all headcount into one number:

1. `Norm` — governed staffing capacity/target.
2. `HR Actual` — official HR snapshot, including FTE and source/freshness evidence.
3. `Employee Master Actual` — currently active operational identity authority.
4. `Incoming Committed` — employees with a confirmed future employment start.
5. `Confirmed Exits` — active employees with a confirmed future employment end.
6. `Committed HC` — current operational actual + starts - confirmed exits.
7. `Open Requisitions` — approved/open headcount not yet committed as employees.
8. `Uncovered Gap` — norm not covered by committed HC or already-open requisitions.
9. `30/60/90 Gap` — future uncovered gap after confirmed starts/exits.

HR Actual is currently a reconciliation authority, not a silent replacement for
Employee Master decision authority. Promotion requires customer-file
reconciliation, scope/PII/security acceptance and explicit evidence gates.

## Orchestrator priority order

The Workforce/Hiring orchestrator must use this priority on every development
session:

1. Repair any current exact-head RED regression before feature work.
2. Preserve canonical Employee Master and tenant/RLS/security boundaries.
3. Close market-parity `GAP` items that unlock end-to-end user outcomes.
4. Productize already-built backend intelligence before inventing another engine.
5. Connect Hiring and Workforce through committed HC, demand and Day-One outcome.
6. Add EAY differentiation only on top of a tested parity capability.
7. Accumulate Final Evidence Pack assets as the feature is built.
8. Never mark field/production acceptance complete from synthetic proof.

## Next execution tranches

### P0 — Staffing truth and vacancy integrity

- HR Actual reconciliation and freshness gate.
- Committed HC + 30/60/90 uncovered-gap visibility.
- Norm/Actual/Committed shown on every vacancy decision.
- Duplicate/open requisition protection and stale-actual warning.
- Customer HR-file acceptance pack.

### P1 — Frontline hiring parity

- Mobile/QR apply.
- Structured eligibility screening.
- Interview self-scheduling.
- Offer/acceptance state machine.
- Candidate reminders and no-show recovery.
- Need-to-Day-One funnel analytics.

### P1 — Employee flexibility parity

- Availability and preferred hours.
- Open-shift marketplace.
- Governed shift swap.
- Skill/certification eligibility.
- Fairness and fatigue-aware ranking.

### P1 — Live Workforce Command Center

- Required / scheduled / checked-in / available / absent / on-leave.
- Demand variance and coverage risk by interval.
- Overtime/fatigue risk.
- Explainable recommended action and expected KPI impact.
- Human approval before roster authority changes.

### P2 — EAY category-leadership loop

- Hiring need from operational demand + attrition + committed HC.
- Source quality measured through Day 7/30/90 outcomes.
- Planner override learning tied to measured results.
- Jarvis explanations grounded in exact staffing/demand evidence.
- Budget/OPEX and customer KPI impact attached to workforce decisions.

## Production-truth gates

These remain external until real evidence exists:

- Corporate OIDC / workload identity and exit revocation.
- Real iOS App Attest and Android Play Integrity.
- Physical-device biometric presence abstraction.
- Warehouse GPS/geofence and spoof/failure observations.
- Customer HR/roster/leave/attendance reconciliation.
- Staging concurrency, restart, backup/isolated restore and RPO/RTO.
- Penetration, accessibility, language and field UAT.

Passing repository CI is required, but never sufficient, for production readiness.
