# DockOS production infrastructure acceptance

Canonical line: PR #1 → PR #60. Production readiness must remain false until every mandatory external gate below has real staging/pilot evidence.

## Environment identity and trust

- [ ] Corporate OIDC issuer, audience and JWKS are the real corporate tenant values.
- [ ] Real user login succeeds with expected email/subject/role claims.
- [ ] Supplier token cannot obtain admin access.
- [ ] Tenant mismatch fails closed.
- [ ] Expired/invalid token fails closed.
- [ ] Signed gateway request succeeds with the current secret.
- [ ] Exact replay of timestamp + nonce + signature is rejected.
- [ ] Previous gateway secret is accepted only during the documented rotation window.
- [ ] Previous secret is removed after rotation and subsequently rejected.

Evidence: timestamp, staging URL identifier, OIDC tenant/app identifier, anonymized subject/email, HTTP status matrix, gateway rotation change record. Never attach raw tokens or secrets.

## BigQuery production PO identity

- [ ] Production workload/service identity is documented and least-privilege IAM is approved.
- [ ] `DOCKOS_PO_SOURCE=BIGQUERY`.
- [ ] `LOCAL`/mock/example fallback is disabled in production.
- [ ] Protected live PO request returns `source=BIGQUERY`.
- [ ] Returned PO has stable source identity and sync timestamp.
- [ ] Supplier A cannot see Supplier B PO rows.
- [ ] Supplier/DC scope is enforced on the BigQuery-backed response.
- [ ] BigQuery outage causes fail-closed behavior; stale mock/LOCAL PO is not silently substituted.
- [ ] Recovery after BigQuery restoration succeeds and sync lag returns below the agreed threshold.

Evidence: workload identity name, IAM role list, redacted query/job ID, PO source response, outage/recovery timestamps.

## SMTP and durable notification acceptance

Use designated staging supplier/DC mailboxes only.

- [ ] Reservation-created email delivered.
- [ ] 48h reminder delivered once.
- [ ] 24h/final reminder delivered once.
- [ ] Edit notification delivered once and old pending reminders are cancelled/replaced correctly.
- [ ] Cancellation notification delivered once.
- [ ] Temporary SMTP failure enters retry with backoff.
- [ ] Retry eventually reaches SENT after SMTP recovery.
- [ ] Repeated permanent failure reaches DEAD at the configured terminal threshold.
- [ ] Duplicate worker/process execution does not produce a duplicate logical notification.
- [ ] Stable Message-ID / idempotency key is visible in delivery evidence.

Evidence: reservation number, event, outbox state transitions, attempt count, Message-ID, inbox received timestamp. Do not attach mailbox credentials.

## PostgreSQL, multi-worker and concurrency

- [ ] Real staging PostgreSQL endpoint uses migrations `001_dockos_postgres` and `002_runtime_hardening`.
- [ ] Tenant RLS is active under the runtime database role.
- [ ] At least 4 backend workers/pods are deployed concurrently.
- [ ] Same-slot high-concurrency race never exceeds configured pallet/SKU capacity.
- [ ] Supplier daily-limit race never exceeds configured daily limit across different slots.
- [ ] Same PO can be consumed by only one active reservation.
- [ ] DB pool saturation remains below the agreed operational limit under pilot load.
- [ ] Lock contention p95/p99 is recorded.
- [ ] Reservation latency p50/p95/p99 is recorded.
- [ ] Failed-booking count and reason distribution are recorded.

Evidence: deployment replica count, load parameters, approved/rejected counts, p50/p95/p99 latency, lock wait p95/p99, pool saturation, database query/lock snapshot.

## Resilience and DR

- [ ] Network interruption causes write paths to fail closed.
- [ ] Network restoration recovers without manual state repair.
- [ ] PostgreSQL restart causes temporary failure only and reconnects successfully.
- [ ] BigQuery outage is fail-closed and recovers after source restoration.
- [ ] SMTP outage retains durable notification state and retries after recovery.
- [ ] `pg_dump`/managed backup is produced from the staging production-like database.
- [ ] Restore is rehearsed into an isolated database.
- [ ] Migration versions, supplier access, PO state, reservations, outbox and audit evidence survive restore.
- [ ] RTO and RPO are measured and approved.

Evidence: outage timeline, recovery timeline, RTO/RPO, backup identifier, restore database identifier, post-restore row/invariant checks.

## SLO / observability acceptance

The `/api/dockos/ops/metrics` surface must be scraped only through the trusted internal path.

Mandatory metrics:

- `dockos_reservation_latency_p50_ms`
- `dockos_reservation_latency_p95_ms`
- `dockos_reservation_latency_p99_ms`
- `dockos_lock_wait_p95_ms`
- `dockos_lock_wait_p99_ms`
- `dockos_failed_bookings_total`
- `dockos_outbox_oldest_age_seconds`
- `dockos_notification_retry_total`
- `dockos_notification_dead_total`
- `dockos_bigquery_sync_lag_seconds`
- `dockos_db_pool_saturation_ratio`
- `dockos_db_pool_requests_waiting`

- [ ] Metrics are scraped from every worker/pod or aggregated by the platform observability layer.
- [ ] Dashboard exists for the mandatory metrics.
- [ ] Alert thresholds and ownership are documented.
- [ ] One synthetic alert test reaches the operational owner.

## Supplier/DC pilot acceptance

Pilot requires at least one real supplier identity and one real DC mapping.

- [ ] Supplier can see only assigned supplier(s) and DC(s).
- [ ] Supplier sees only eligible open BigQuery POs.
- [ ] Supplier creates a valid reservation from an eligible PO.
- [ ] Capacity shown before booking matches backend-authoritative post-booking state.
- [ ] Daily limit blocks the next reservation at the exact limit.
- [ ] Supplier edit/cancel policy behaves correctly before/after cutoff.
- [ ] DC admin can edit/cancel with reason and audit identity.
- [ ] 48h/24h/edit/cancel notifications reach the designated real staging mailboxes.
- [ ] KPI surface reflects the same reservation state after refresh/restart.
- [ ] Arabic RTL and TR/EN/DE views are sanity-checked on the pilot UI.
- [ ] Pilot user signs off supplier workflow.
- [ ] DC operations owner signs off dock workflow.

## Readiness decision

DockOS may be reported at **≥95% production readiness only if all mandatory groups PASS**: PostgreSQL, real OIDC, real signed gateway, real BigQuery identity, real SMTP, multi-worker load/concurrency, DR/resilience, observability and supplier/DC operational pilot.

Fake/example SMTP, LOCAL PO fallback, missing workload identity, missing staging credentials, skipped DR, skipped load or skipped operational pilot are hard blockers. A repository-only CI pass is not equivalent to production infrastructure acceptance.
