# EAY Hiring Final Main Acceptance v1

## Release intent

This document records the final repository-level Hiring acceptance boundary. It does not activate production infrastructure and does not authorize any credential/session automation against e-Devlet.

## Current composition truth

- Current main authority observed at preparation: `624390d24142b5768e4d5a9a32de34fb68ebe00d`.
- Final Hiring production-authority lineage head: `d23d71ff193c1ab1c856cbc1e00e83b6c01057c9`.
- GitHub compare proves the Hiring head is a real ancestor of current main: main is ahead and Hiring is zero commits behind.
- Therefore Hiring code reached main through later cumulative release composition even though historical stacked PR #172 remains open/unmerged against its old parent branch.

## Hiring repository acceptance already proven on exact Hiring head

The exact Hiring head completed all required repository-controlled gates successfully:

- EAY Hiring Production Authorities — SUCCESS
- EAY Hiring UI Gateway — SUCCESS
- DockOS full-stack validation — SUCCESS
- PostgreSQL role/RLS/replay/concurrency — SUCCESS
- V47 offer/communication/talent/offboarding acceptance — SUCCESS
- automatic reminder planner acceptance — SUCCESS
- Recruitment → Workforce offboarding closure acceptance — SUCCESS
- credential-free official portal human-assist contract — SUCCESS

## e-Devlet production model

Institutional M2M is optional automation, not a Hiring product blocker.

Supported non-M2M production flow:

1. Candidate opens the official e-Devlet portal in a separate `noopener noreferrer` tab.
2. Password, OTP, CAPTCHA, cookies and authenticated e-Devlet browser state remain exclusively with the user and e-Devlet.
3. Candidate downloads the official barcode/QR document and explicitly selects it in the EAY candidate portal.
4. EAY applies the one-time upload capability, encrypted evidence quarantine, malware/scanner release, exact evidence binding, official human verification and second-authority attestation gates.
5. EAY never imports or automates the user's e-Devlet session.

Institutional OAuth2/mTLS/provider-signature integration may later automate the official verification step when an authorized contract and credentials exist, without changing this fail-closed trust boundary.

## Current main regression boundary

Current main contains the final candidate handoff implementation and the corrected human-assist contract test. Later cumulative main changes do not remove the final Hiring lineage. The final main PR must pass the repository's existing main security gates, including EAY Pre-Pentest Security Acceptance.

## Readiness

Repository status: **INTEGRATION VERIFIED / RELEASE CANDIDATE**.

`PRODUCTION ACCEPTED` remains an environment/operations claim and requires organization-controlled production provisioning, identities, keys, monitoring and operational acceptance.
