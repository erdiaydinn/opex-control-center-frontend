# EAY Academy media / CDN production acceptance

This document is an acceptance contract, not evidence that a real CDN has already passed. Academy is not production-ready on media delivery until the staging/production-like observations below are attached to the canonical PR.

## Data-plane invariant

The Core API authorizes playback; it does not proxy video bytes. Originals remain private in object storage, adaptive HLS/DASH renditions are delivered through the CDN/origin-shield path, and the object-storage origin must reject direct public access. A 1,200-viewer event must therefore load the CDN, not Core API workers.

## Authorization propagation

A signed grant on the top-level HLS manifest is insufficient by itself. Relative HLS variant and segment URIs do not reliably inherit a manifest query token. Production acceptance therefore requires one proven propagation mechanism end-to-end, for example CDN signed cookies, edge/session authorization, authenticated manifest rewriting, or a player/edge contract that appends the short-lived token to every protected child request.

`ops/load/k6-academy-playback-flow.js` is the canonical negative/positive propagation check. It requests a real Academy playback grant, follows the returned manifest, resolves child URIs using browser-like relative URL behavior, follows one variant playlist when present, and requires the resulting media segment to remain authorized. If the manifest succeeds but the child/segment is 401/403, media authorization is incomplete and release remains blocked.

The edge must additionally prove that an equivalent protected segment without authorization is rejected. Authorization must be validated before cache delivery; the authorization token must not become part of the origin object identity. For query-token deployments, the CDN cache key must explicitly exclude the token after edge authorization so viewer-specific tokens do not destroy cache efficiency.

## Download-friction controls

Required controls are private origin, short-lived playback authorization, HTTPS-only delivery, HLS/DASH segmentation, no raw bucket/object coordinates in learner APIs, no-store authorization responses, and CDN/origin logging rules that redact authorization material. These controls provide friction and access control; they are not a claim that browser-delivered media is impossible to capture.

## 1,200 concurrent-video model

Planning model:

- 1,200 concurrent viewers.
- 6-second media segments.
- ~1.5 Mbit/s average video bitrate; ~2.5 Mbit/s p95 planning bitrate.
- ~1.8 Gbit/s average CDN egress and ~3.0 Gbit/s p95 planning egress.
- ~200 video-segment requests/s at the nominal 6-second cadence before audio/text tracks, ABR switches, retries and seeks.
- Edge stress envelope: 400 RPS sustained and 600 RPS burst.
- 90-second playback-grant refresh: ~13.3 authorization RPS average for 1,200 active sessions; API acceptance remains 50 RPS sustained / 200 RPS burst.

The CDN test must be run from more than one load-generator location when possible. A single runner is not sufficient evidence for 1,200 geographically distributed viewers.

## Required evidence

Release evidence must record CDN/vendor configuration version, object-storage private-origin policy, edge-auth mechanism, cache-key policy, representative media/rendition ladder, load-generator regions, test timestamp and exact application SHA. At minimum capture authorization p95/p99, manifest p95/p99, segment p95/p99, error rate, 401/403 negative-control result, steady-state cache-hit ratio, origin request rate/egress, CDN egress, startup time and rebuffer/error observations.

Pass targets are: auth error <1%, auth p95 <500 ms / p99 <1 s, edge segment error <1%, edge p95 <250 ms / p99 <500 ms for the stress contract, steady-state segment cache hit >=95%, unauthorized segment denied, and no object-storage coordinates or authorization material exposed in learner-visible payloads/log samples.

## Current status

GitHub CI validates the backend media authorization contract and the load scripts can be syntax-gated, but CI cannot substitute for a real object store/CDN. Until a real staging CDN executes the propagation, negative-auth and load tests above, media delivery remains an explicit external production blocker.
