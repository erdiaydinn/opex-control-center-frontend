# EAY Academy production architecture

## Trust and persistence

Academy runs inside Platform Core authenticated tenant context. PostgreSQL is authoritative for content metadata and immutable versions, media metadata, learning paths, role/manual enrollments, resumable progress, quiz versions/attempts, certificates/revocation, resource entitlements, SOP/document chunks and learning audit. Every Academy table uses PostgreSQL `FORCE ROW LEVEL SECURITY`; runtime remains `NOSUPERUSER NOBYPASSRLS`.

Tenant module licensing is checked through `tenant_entitlements(module_key='academy')`. Resource access is separately constrained by active enrollment or Academy resource entitlement. Missing scope is denial, never global fallback.

## Media data plane

The application server is not a video origin. Originals live in a private object store (S3/GCS/Azure/MinIO contract), are transcoded to adaptive HLS/DASH, and are served through CDN/origin shield. The API only performs authorization after tenant, learner, publication and entitlement/enrollment checks.

Playback grants are HMAC-SHA256 signed and bound to tenant, subject, media ID, exact content-version ID and delivery-key hash. TTL is restricted to 30–300 seconds and the signing secret is file-backed for secret-manager mounting. Learner APIs never expose raw bucket/object coordinates. These controls create download friction; they cannot guarantee browser-delivered video is impossible to capture.

## Scale model: ~2,000 users / ~1,200 concurrent video sessions

Planning assumptions: 1,200 simultaneous viewers, six-second segments, ~1.5 Mbit/s average bitrate and ~2.5 Mbit/s p95 planning bitrate. This is ~1.8 Gbit/s average CDN egress and ~3.0 Gbit/s p95 planning egress. Six-second video segments imply ~200 segment requests/s before audio/text, ABR changes and retry overhead; edge tests therefore target 400–600 requests/s. At 1.5 Mbit/s, 1,200 viewers are ~202.5 GB per 15 minutes or ~810 GB/hour continuously.

A 90-second playback grant refresh across 1,200 sessions averages ~13.3 API authorization requests/s. API load tests target 50 RPS sustained and 200 RPS burst. CDN edge tests are separate and target >=95% steady-state segment cache hit so origin is not the data plane.

## Learning lifecycle

Paths pin exact published `content_version_id`s. Role assignment reconciles to durable enrollment. Progress combines idempotency keys and optimistic revision checks; stale writers get HTTP 409. Required checkpoint quizzes block playback/progress beyond their timeline position until passed. Quiz attempts bind to exact immutable quiz versions and grade server-side; correct-option flags are never exposed. Completion requires every required version and active published required quiz, then fingerprints tenant, subject, path, exact versions and exact quiz IDs. Completion and certificate can be revoked with durable actor/reason evidence.

## Grounded SOP/document Q&A

Document/SOP chunks live in tenant-scoped PostgreSQL full-text evidence. Retrieval is limited to published versions visible via enrollment/resource entitlement. Foundation Q&A is deliberately extractive: absent evidence returns unsupported rather than invented company policy. Supported responses expose content ID, exact content-version ID, version label/number, SHA-256, page/anchor and chunk identity.

## Language, RTL and accessibility

Metadata locales are limited to TR/EN/DE/AR; Arabic is declared RTL in the API contract. Content versions carry accessibility metadata. Production acceptance must validate captions/transcript coverage, document readability/tagging, keyboard navigation, focus semantics, contrast and screen-reader behavior in staging; backend metadata alone is not a WCAG-compliance claim.
