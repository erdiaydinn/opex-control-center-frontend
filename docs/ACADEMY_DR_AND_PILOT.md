# EAY Academy DR, media and staging acceptance

## CI recovery contract

Academy CI applies Platform Core + Academy migrations on PostgreSQL 16, seeds Academy evidence, performs `pg_dump`, restores into a fresh database and verifies Academy data and the Alembic head. This proves schema/data portability only; it does not replace production encryption, off-site retention, object-storage replication or an operator-led restore drill.

## Staging pilot gate before >=95

Staging must use company OIDC, real tenant/role claims, private media storage and the selected CDN. Acceptance must cover role assignment/removal, manual enrollment, content-version replacement without historical rewrite, checkpoint resume across devices, duplicate progress/quiz retries, stale revision conflicts, token expiry/refresh during playback, certificate issue/revocation, tenant A/B negative access, SOP source/version display, TR/EN/DE/AR including Arabic RTL, keyboard/screen-reader behavior and caption/transcript playback.

Media load acceptance is separate from API load. The app server authorizes sessions but never proxies HLS/DASH segment bytes. Record auth latency/error rate, CDN cache hit, edge/origin rates, bitrate, startup/rebuffer, segment 4xx/5xx, token-refresh failures and origin egress.

## External blockers

Real object-store policies, CDN distribution/edge token validation, secret-manager injection, production OIDC mapping, transcode pipeline, a real 1,200-concurrent CDN run, staging accessibility/RTL pilot, production backup retention and an operator-led restore drill require external environment evidence. Readiness remains below 95 until these are demonstrated.
