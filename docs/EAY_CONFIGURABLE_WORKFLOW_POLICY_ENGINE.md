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

## Registered adapter boundary

An `ActionIntent` is not execution authority by itself. Before handoff, the platform must resolve exactly one enabled `RegisteredActionAdapter` matching the intent's action key, action type, effect and execution mode. Zero matches and multiple matches both fail closed.

Adapter registrations describe only named internal capabilities: adapter id, target module, capability id, allowed effects/modes, optional required Platform Core permission, authoritative domain guard id and idempotency requirement. Provider URLs, credentials, scripts, commands and executable code are deliberately absent from the registration model.

Automatic high-risk adapter registrations are invalid. A domain-action adapter cannot authorize automatic mutation. Dry-run and proposal-only intents cannot produce execution handoffs. Approval-required intents must carry a matching same-tenant approved decision before handoff. If an adapter declares a required permission, the handoff includes only a fingerprint of the granted permission set rather than raw authorization material.

The resulting adapter handoff is deterministic and carries tenant, intent/dedupe identity, adapter/capability/domain-guard identifiers, bounded action parameters and decision provenance. It does not call the provider. The receiving adapter must still re-apply the target module's domain guard and idempotency contract. Repository adapter registration therefore proves a safe routing contract, not a connected production provider.

## Versioning and governance

Workflow content is immutable and versioned. A revision advances exactly one version and explicitly supersedes the prior version.

Publishing is a separate auditable lifecycle:

`draft → approved → effective → superseded`

A workflow may also be disabled from draft, approved or effective state with an explicit reason. Superseded and disabled states are terminal for that version.

PostgreSQL enforces the governance chain against the actual current status, requires monotonically advancing governance timestamps and prevents the workflow author from approving their own version. This provides a maker-checker baseline instead of treating an editable status column as release authority.

An approved version cannot become effective until a reviewed simulation artifact exists for the same tenant, workflow and candidate version. The review binds the baseline/candidate versions, impact fingerprint, simulated sample count, changed-event count, high-risk changed-event count, reviewer and review time. High-risk changes require explicit acknowledgment. Simulation evidence is append-only and tenant isolated.

## Resolution semantics

Live evaluation resolves only effective policies for the same tenant, source module, event type, effective time and matching scope. Scope may include country, region, business unit and location.

More specific scope wins, then higher version. Equally authoritative candidates fail closed instead of being selected nondeterministically.

Missing facts do not satisfy comparison rules. Event-fact fingerprints are verified before evaluation. Exclusive-group ambiguity fails closed.

## Simulation, canary impact and change safety

Draft, approved and effective workflow versions may be evaluated in explicit dry-run mode for a chosen effective time. Superseded or disabled versions are not treated as current simulation candidates.

Dry-run and live evaluations produce distinct action-intent/dedupe identities. Simulation therefore cannot consume or block a future live side effect. Dry-run action intents cannot receive execution authority.

Candidate-vs-baseline comparison uses semantic action signatures rather than version-derived intent IDs. A no-op version bump is therefore reported as unchanged. Threshold/rule changes show only the affected events and added/removed semantic actions. New financial, employment or security effects mark the impact as high risk and require explicit review acknowledgment before activation.

Simulation batches are bounded and event facts are evaluated in memory; the impact artifact stores fingerprints/counts and review provenance rather than creating a new raw-event archive. Scope changes require a separate scoped impact review instead of being silently compared as if the affected population were unchanged.

This supports historical replay, pre-publish impact review and future shadow/canary evaluation without silently changing production behavior.

## Persistence and replay protection

The PostgreSQL authority stores:

- immutable workflow definitions and rule content;
- append-only governance events;
- event receipts with source/scope/provenance and a facts fingerprint, not raw event facts;
- deterministic evaluation fingerprints;
- action intents with dedupe keys;
- approval/rejection decisions;
- append-only simulation reviews used to authorize effective promotion.

Event id and idempotency key are unique per tenant. Action dedupe keys are unique per tenant. All authority tables use forced tenant RLS and append-only update/delete guards.

Database constraints repeat critical application-level safety rules: high-risk automatic actions are rejected, direct automatic domain mutation is rejected, high-risk intents require approval, unsafe action-parameter payloads are rejected, invalid governance chains are rejected, live evaluation of non-effective policies is rejected, dry-run/proposal-only intents cannot receive execution approval, and approved policies cannot become effective without reviewed simulation evidence.

## Example compositions

Customer Promise can emit `customer_promise.deviation_detected`; Item 7 may automatically notify operations, create a review task or propose a financial recovery. It cannot issue the refund itself and cannot bypass Customer Promise approval.

Workforce can emit depot-pressure or capacity events; Item 7 may notify, create a task or propose a replan. Workforce hard legal constraints, schedule authority and manager approval remain authoritative.

Field Intelligence can emit overdue/rejected-evidence events; Item 7 may schedule reminders, escalations or rechecks while Field Intelligence remains authoritative for mission state and evidence verification.

Inventory can emit variance/exception events; Item 7 may create review work but may not directly adjust stock truth.

Jarvis may explain why a rule matched from the deterministic trace, and may help an authorized user draft a rule version, but Jarvis does not silently publish or execute high-risk workflow changes.

## Repository acceptance for Item 7

Repository-ready acceptance requires deterministic rule evaluation, tenant/scope/version resolution, ambiguity rejection, event-fingerprint validation, strict payload safety, immutable versioning, auditable governance, maker-checker approval, dry-run/live separation, semantic candidate-vs-baseline impact diff, simulation-gated effective promotion, explicit high-risk acknowledgment, exact registered-adapter resolution, permission/domain-guard handoff enforcement, PostgreSQL append-only persistence, tenant zero-read/zero-write proof, event/action replay protection, database restart durability and isolated backup/restore rehearsal.

Repository/CI proof is not production acceptance.

## Runtime integration boundary

The canonical engine source currently lives under `backend/app/platform/workflow_policy`. Platform Core remains the browser-facing identity/tenant/permission authority. A Core runtime adapter must consume this single canonical engine source or a versioned package built from it; copying/reimplementing the evaluator inside Core is forbidden. The legacy backend must not gain a competing browser-facing workflow authorization path.

Until the Core deployment/build context and registered action-adapter wiring are verified in the production-shaped runtime, repository engine success must not be reported as an active production automation service.

## External production acceptance still required

Production readiness additionally requires canonical Platform Core identity/permission mapping, verified single-source Core runtime packaging, real event-source contracts, concrete registered adapters wired to real notification/task/domain providers, retry/dead-letter behavior, production audit/observability, customer-specific maker-checker roles, staging replay with representative events, policy-author UAT, controlled canary/shadow evaluation, production-shape throughput/load tests, backup/restore evidence and module-by-module acceptance of every side-effect adapter.

No arbitrary webhook/command/SQL executor should be added as a shortcut around the registered-adapter model.

`production_ready` remains false until the relevant real-environment evidence passes.
