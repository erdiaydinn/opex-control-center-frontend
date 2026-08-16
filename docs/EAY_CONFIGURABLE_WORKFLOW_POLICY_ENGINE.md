# EAY Configurable Workflow / Policy Engine — Product Lifecycle Item 7

## Product intent

EAY Workflow / Policy Engine turns governed operational events into deterministic, auditable action intents without becoming a second identity system, a second module database, or an unrestricted automation runtime.

The canonical loop is:

`Authorized Event → Effective Policy Resolution → Deterministic Conditions → Action Intents → Approval when required → Registered Adapter → Module Authority → Audit / Learning`

The engine is a shared platform capability. Commercial modules remain independently useful and continue to own their domain truth.

## Authority boundary

The engine decides **whether a governed action should be proposed or requested**. It does not silently mutate authoritative module state.

Existing domain authority remains unchanged:

- Workforce owns scheduling hard constraints, employee/shift lifecycle, legal and attendance truth.
- Field Intelligence owns mission/target lifecycle, evidence and verification truth.
- Customer Promise owns promise/deviation truth and its financial recovery approval boundary.
- Inventory owns stock/count/reconciliation authority.
- DockOS owns receiving/dock operational truth.
- Academy owns learning/progress/certificate truth.
- Platform Core owns authentication, tenant authority, permissions and shared audit identity.

Item 7 may orchestrate these domains through registered adapters, but it may not weaken their validations, maker-checker controls, tenant isolation or hard legal/security constraints.

## Safe rule language

The engine intentionally does not provide arbitrary Python/JavaScript execution, expression `eval`, SQL execution, shell commands, arbitrary HTTP endpoints or user-supplied webhook URLs.

Rules use a fixed declarative vocabulary:

- conditions: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `exists`;
- match modes: `all`, `any`;
- deterministic priority and optional stop-processing;
- optional exclusive groups where multiple simultaneous matches fail closed;
- action types: notification, task creation, approval request, domain-action proposal and scheduled recheck.

Event facts and action parameters are scalar, bounded and schema constrained. Raw credentials, authorization headers, customer contact/address fields, executable commands, raw SQL and arbitrary URLs are rejected. Safe derived signals such as `token_age_seconds`, `endpoint_health` or `sql_latency_ms` may be used without exposing the underlying credential, endpoint or query.

## Risk classes and execution

Every action declares an effect and execution mode.

Effects are informational, operational, financial, employment or security. Execution modes are automatic, requires-approval or proposal-only.

Financial, employment and security actions cannot be automatic. A domain mutation expressed as `propose_domain_action` cannot be automatic even when its effect is only operational. Proposal-only intents can never pass the generic execution guard. Dry-run intents can never execute.

A registered downstream adapter must still apply the target module's authorization and domain rules. Generic workflow approval is not a substitute for Customer Promise recovery approval, Workforce legal constraints, Inventory reconciliation authority or another module-specific control.

## Versioning and governance

Workflow content is immutable and versioned. A revision advances exactly one version and explicitly supersedes the prior version.

Publishing is a separate auditable lifecycle:

`draft → approved → effective → superseded`

A workflow may also be disabled from draft, approved or effective state with an explicit reason. Superseded and disabled states are terminal for that version.

PostgreSQL enforces the governance chain against the actual current status, requires monotonically advancing governance timestamps and prevents the workflow author from approving their own version. This provides a maker-checker baseline instead of treating an editable status column as release authority.

## Resolution semantics

Live evaluation resolves only effective policies for the same tenant, source module, event type, effective time and matching scope. Scope may include country, region, business unit and location.

More specific scope wins, then higher version. Equally authoritative candidates fail closed instead of being selected nondeterministically.

Missing facts do not satisfy comparison rules. Event-fact fingerprints are verified before evaluation. Exclusive-group ambiguity fails closed.

## Simulation and change safety

Draft, approved and effective workflow versions may be evaluated in explicit dry-run mode for a chosen effective time. Superseded or disabled versions are not treated as current simulation candidates.

Dry-run and live evaluations produce distinct action-intent/dedupe identities. Simulation therefore cannot consume or block a future live side effect. Dry-run action intents cannot receive execution authority.

This supports historical replay, change-impact review and future shadow/canary evaluation without silently changing production behavior.

## Persistence and replay protection

The PostgreSQL authority stores:

- immutable workflow definitions and rule content;
- append-only governance events;
- event receipts with source/scope/provenance and a facts fingerprint, not raw event facts;
- deterministic evaluation fingerprints;
- action intents with dedupe keys;
- approval/rejection decisions.

Event id and idempotency key are unique per tenant. Action dedupe keys are unique per tenant. All authority tables use forced tenant RLS and append-only update/delete guards.

Database constraints repeat critical application-level safety rules: high-risk automatic actions are rejected, direct automatic domain mutation is rejected, high-risk intents require approval, unsafe action-parameter payloads are rejected, invalid governance chains are rejected, live evaluation of non-effective policies is rejected, and dry-run/proposal-only intents cannot receive execution approval.

## Example compositions

Customer Promise can emit `customer_promise.deviation_detected`; Item 7 may automatically notify operations, create a review task or propose a financial recovery. It cannot issue the refund itself and cannot bypass Customer Promise approval.

Workforce can emit depot-pressure or capacity events; Item 7 may notify, create a task or propose a replan. Workforce hard legal constraints, schedule authority and manager approval remain authoritative.

Field Intelligence can emit overdue/rejected-evidence events; Item 7 may schedule reminders, escalations or rechecks while Field Intelligence remains authoritative for mission state and evidence verification.

Inventory can emit variance/exception events; Item 7 may create review work but may not directly adjust stock truth.

Jarvis may explain why a rule matched from the deterministic trace, and may help an authorized user draft a rule version, but Jarvis does not silently publish or execute high-risk workflow changes.

## Repository acceptance for Item 7

Repository-ready acceptance requires deterministic rule evaluation, tenant/scope/version resolution, ambiguity rejection, event-fingerprint validation, strict payload safety, immutable versioning, auditable governance, maker-checker approval, dry-run/live separation, high-risk approval boundaries, PostgreSQL append-only persistence, tenant zero-read/zero-write proof, event/action replay protection, database restart durability and isolated backup/restore rehearsal.

Repository/CI proof is not production acceptance.

## External production acceptance still required

Production readiness additionally requires canonical Platform Core identity/permission mapping, real event-source contracts, registered action-adapter allowlists, real notification/task providers, retry/dead-letter behavior, production audit/observability, customer-specific maker-checker roles, staging replay with representative events, policy-author UAT, controlled canary/shadow evaluation, production-shape throughput/load tests, backup/restore evidence and module-by-module acceptance of every side-effect adapter.

No arbitrary webhook/command/SQL executor should be added as a shortcut around the registered-adapter model.

`production_ready` remains false until the relevant real-environment evidence passes.
