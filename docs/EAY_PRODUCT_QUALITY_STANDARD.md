# EAY Product Quality Standard

## Status

This standard is a release requirement, not a design aspiration. A module is not
accepted because it builds, because its backend tests pass, or because its UI is
visually attractive. EAY acceptance requires the complete chain:

`correct behavior → authoritative data → security/scope → resilience → usable interaction → visual quality → accessibility → performance → auditability → real-user evidence`.

Repository evidence may prove repository readiness. It may never be represented
as production or market-leading evidence when external/field proof is missing.

## Non-negotiable product rules

1. **Task-first design.** The most common operational task must dominate the
   screen. Dashboards, decoration and secondary information may not slow the
   primary task.
2. **Role-specific surfaces.** Desktop manager, employee mobile, supplier,
   shared terminal and warehouse handheld experiences are different products on
   one backend truth; one responsive screen must not be stretched across all of
   them when the job differs.
3. **No duplicate truth.** Frontends do not implement shadow KPI formulas,
   authorization rules, Employee Master identity, finance truth or tenant scope.
4. **Fail closed, explain clearly.** A denied or failed action must explain what
   happened, preserve user work where safe, and provide a recovery path.
5. **All states are designed.** Loading, empty, partial, stale, offline,
   conflict, retry, permission-denied and error states are part of the product.
6. **Accessibility is core product behavior.** Web targets WCAG 2.2 AA as the
   minimum release baseline, with additional EAY requirements for screen readers,
   keyboard/switch/voice operation, visible focus, forced-colors, reduced motion,
   large targets, no color-only meaning, scalable text, media alternatives and
   cognitive focus modes. Accessibility is not an optional theme.
7. **Accessibility preferences do not require medical disclosure.** A user may
   select captions, audio description, reduced motion, text size, contrast,
   readable typography or other access preferences without declaring a disability
   or health diagnosis. Sensitive diagnosis data is not required for the product
   to adapt.
8. **Global localization is first class.** The platform baseline is
   TR/EN/DE/AR/FR/ES/IT/NL/PL/PT-BR. Arabic RTL is structural, not text-only.
   Customer tenants may restrict the languages enabled for their organization,
   but shared EAY components may not hard-code customer-facing copy.
9. **EAY branding is canonical for new product surfaces.** Historic OPEX names
   may survive in internal identifiers during migration, but customer-facing new
   design must converge on EAY.
10. **Evidence before claims.** "Best", "production ready" and >=95% readiness
   require real field evidence against the acceptance matrix.

## Inclusive Experience Standard

EAY must not create a separate "disabled version" of the product. The same
product must remain operable and understandable for users with permanent,
temporary or situational access needs.

### Visual and blind/low-vision users

- semantic headings, landmarks, labels, descriptions and live regions;
- screen-reader-compatible names and state announcements;
- keyboard-visible focus and predictable focus restoration;
- high contrast and operating-system forced-colors support;
- text scaling and reflow without loss of task functionality;
- status/error meaning never communicated by color alone;
- charts and visual analytics provide textual/table equivalents;
- video that contains important visual information supports audio description or
  a descriptive transcript.

### Deaf and hard-of-hearing users

- captions for speech and relevant non-speech audio when media contains audio;
- transcripts for recorded learning content;
- descriptive transcripts for users who need both audio and visual information in
  text form;
- visual equivalents for operational sound alerts;
- sign-language track/picture-in-picture capability when required by the audience
  or customer policy.

### Motor access

- all critical flows operable without a pointer;
- keyboard, switch and voice-control semantics use stable accessible names;
- minimum 48dp touch targets on mobile/terminal primary actions;
- drag-and-drop always has a non-drag alternative;
- no precision-pointer-only gestures for critical operations;
- destructive controls are not placed where accidental activation is likely.

### Cognitive, learning and neurodivergent users

- consistent navigation and terminology across modules;
- focus/simplified mode that removes non-essential visual noise;
- readable-font and text-spacing options without breaking layout;
- complex instructions are chunked into explicit steps;
- plain-language rendering capability for eligible explanatory content;
- Academy learning supports pause/resume, adaptive review and configured
  assessment accommodations without exposing unnecessary medical information.

### Motion, vestibular sensitivity and photosensitivity

- operating-system `prefers-reduced-motion` is respected;
- user can force reduced motion regardless of OS setting;
- essential information never depends on animation/parallax;
- unsafe flashing patterns are forbidden;
- decorative motion and blur may be removed by focus mode.

## Measurable product targets

These are acceptance targets. CI can protect contracts; real-device/field tests
must provide the final measurements.

- Critical-task success: **>=98%** without operator assistance.
- Usability: **SUS >=85** for pilot cohorts on the intended device/role.
- Crash-free sessions: **>=99.8%** during pilot/staging observation.
- Mobile/terminal interactive targets: **>=48dp**.
- Inventory terminal local scan-to-feedback: **p95 <=150ms** on target hardware.
- Inventory terminal cold start: **p95 <=2.5s** on target hardware.
- Offline mutation queues: exactly-once/idempotent replay under duplicate,
  reconnect and process-restart scenarios.
- Destructive actions: explicit confirmation; reversible/compensating path when
  the domain permits it.
- No critical workflow may depend on demo/placeholder data in production shape.

## Surface-specific acceptance

### Workforce + Hiring

Workforce web is a manager operations console; employee mobile is an action-first
personal experience. Hiring remains the same authoritative Employee Master
lifecycle: Norm → Vacancy → Candidate → Evidence → Approval/Reject → Notification
→ Hire → Employee Master → first roster/shift. Exit closes future availability
and device/session authority. Real OIDC, real device attestation, physical
biometric presence, warehouse GPS and real HR files remain mandatory field gates.

### Inventory and Counting

The counting terminal is a **native handheld product surface**, not a small web
page. Acceptance includes hardware scan trigger/DataWedge behavior, one-hand use,
large targets, blind count, unexpected SKU, immediate sound/vibration **and visual**
feedback, offline queue, duplicate/replay safety, rapid recount, supervisor
handoff and recovery after network/app/device restart. The desktop surface is a
dense manager console for assignment, variance, reconciliation, evidence and
approval.

Managed signing, MDM, corporate OIDC, TLS pinning and physical Zebra testing are
real-device gates and may not be replaced with emulator evidence.

### Planogram Studio

Visual polish is invalid without physical truth. SKU dimensions, fixture geometry
and Store DNA must be authoritative before solver quality or 3D appearance can be
claimed. Infeasible placement must explain the violated constraint. 2D and 3D
must represent the same saved planogram version. Drag placement must have a
keyboard/non-drag equivalent for accessible authoring.

### DockOS

Supplier and DC tasks must be fast, explicit and scoped. Capacity edits and bulk
mutations require preview/validation. PO/reservation state, duplicate detection,
amount mismatch handling, notification retry and audit are part of the primary
experience, not admin afterthoughts.

### Budget Intelligence

Finance truth is server-authoritative. Plan → Cost Center → Request → Approval →
PO → Invoice → Actual/Commitment → Forecast → Variance/Reconciliation is one
traceable chain. Financial mutations require scope, four-eyes policy where
configured, durable audit and recoverable import/reconciliation errors.

### Academy

Academy is a learning operating system, not a video library. Content discovery,
playback, interactive authoring, learning paths, adaptive review, quizzes,
progress, field evidence and Jarvis Teacher must feel like one learning product.
Grounded answers show provenance and the exact approved content/version.

A media item is not considered accessibility-complete merely because the video
plays. The media model must support captions, transcript, keyboard-accessible
player controls, audio-description capability and descriptive-transcript
capability. When the target audience/customer requires it, sign-language tracks or
picture-in-picture sign interpretation are supported. Completion cannot depend on
hearing or seeing a single modality when an equivalent accessible learning route
can satisfy the same learning objective.

### Jarvis

Jarvis optimizes for trustworthy completion, not chat novelty. Every data answer
must preserve tenant authority and provenance; high-impact actions remain
approval-bound. Learning/training requires reviewed data, immutable lineage,
offline eval, canary and governed promotion. Live BigQuery evidence cannot be
replaced by synthetic proof.

**Jarvis Security Guardian is EAY platform authority, not a tenant-company tool.**
Its vulnerability intelligence, dependency remediation and platform security
controls are visible/operable only to platform-admin/super-admin authority.
Customer tenants do not approve, suppress or alter EAY platform security posture.
Customer-facing Jarvis may explain the customer's own authorized security or
compliance content only when that capability is explicitly part of the customer
product and tenant scoped.

### Insight / KPI

Insight consumes promoted canonical metric identifiers and provenance. Dashboard
or frontend SQL may not weaken tenant/store/entity scope or create alternate KPI
formulas. Orders/NSFR/PFR/Refund/Prep/Picking/OTP/Putaway become visible as
production truth only after their governed activation evidence passes. Charts must
also expose accessible text/table representations and may not use color as the
only risk/status encoding.

## Field-test scorecard

Each module is tested on its intended device and role. The acceptance record must
contain: build/SHA, environment, device/browser, test identity/tenant/store,
dataset/source version, scenario, expected result, observed result, timing,
operator notes, screenshots/video where permitted, defect ID, retest result and
final owner acceptance.

A field run must cover at minimum:

- happy path and first-use/onboarding;
- permission denied and wrong tenant/store scope;
- loading/empty/partial/stale data;
- offline/network loss/reconnect;
- duplicate request/retry/double tap;
- concurrent edits or stale version conflict;
- process/service/database restart where applicable;
- localization including Arabic RTL and representative long-text locales;
- keyboard-only and screen-reader critical flows on web;
- forced-colors/high-contrast and 200% text/reflow checks;
- reduced-motion behavior;
- captions/transcript/media alternatives in Academy;
- scanner/switch/assistive access behavior appropriate to the surface;
- real error recovery, not just error display.

## Next-phase: Expense Management

Expense Management is intentionally separate from current P0 convergence. Its
planned product chain is:

`receipt/invoice capture → OCR → merchant/date/tax/currency/total/line extraction → per-field confidence → human review/edit → duplicate/policy checks → cost center/category → approval → Budget link → accounting export → evidence/audit`.

Low-confidence OCR may never silently post a financial record. The module will
reuse Employee Master, Approval Engine, Notification Hub, Budget and Audit rather
than create parallel identity, workflow or finance truth.
