# EAY Jarvis Cyber Championship External Authority v1

## Purpose

This contract closes the repository-to-real-run boundary for the EAY Jarvis Cyber World Championship without allowing Jarvis, CI, GitHub Actions, or any competitor to manufacture independent evidence.

The sequence is:

`independent sealed bank → external evaluator authority verification → authorized EAY sandbox → vendor tenant/identity/resource preflight → READY_FOR_REAL_RUNS → real common-harness execution outside the verifier → independent blind scoring`

Repository GREEN proves only that this admission machinery is correct and fail-closed. It does not prove that the race happened.

## Independent evaluator authority

A real sealed bank must be controlled by an evaluator independent of EAY/Jarvis and all named competitors. The authority receipt binds:

- evaluator organization and workload identity references;
- trusted issuer and signing-key fingerprint;
- exact bank fingerprint;
- public manifest, task-set and sealed-ground-truth digests;
- rotation epoch and sealed storage reference;
- evaluator signing key ID and expiry.

The receipt must never contain raw ground truth, private key material, tokens, passwords or signed object URLs. Jarvis may verify the authority; Jarvis may not mint an independent evaluator receipt and call it external evidence.

## Trust policy

The verifier accepts only issuer references and signing-key fingerprints listed in an externally governed trust policy. Known competitor organizations are denied evaluator status. Expired, future, mismatched or untrusted evidence fails closed.

## Vendor authority

CrowdStrike Charlotte AI, Google Security Operations / Gemini and Microsoft Security Copilot each require their own organization-owned authorization and credential-binding receipt.

The credential binding stores only a reference such as `vault://`, `secret-manager://` or `key-vault://`. Raw credentials are forbidden. Each receipt binds:

- competitor;
- organization / tenant / resource;
- workload identity;
- secret-manager reference;
- exact championship environment fingerprint;
- approved read-only operation references;
- authorization evidence and expiry.

Write/admin scope, raw secret material and production mutation authority are hard failures.

## Manual admission workflow

`.github/workflows/jarvis-cyber-championship-run.yml` is `workflow_dispatch` only and uses the protected `cyber-championship` environment on a runner labelled `self-hosted` + `eay-championship`.

The workflow does not accept credentials as user inputs and does not use repository secrets as vendor tokens. It expects an administrator-controlled `EAY_CHAMPIONSHIP_EVIDENCE_DIR` mounted on the authorized runner. The directory contains signed metadata receipts only; no sealed answers or raw credentials are required by the verifier.

The workflow performs admission only. It deliberately stops at `READY_FOR_REAL_RUNS`; repository code does not fabricate private vendor API responses or scores. Real competitor execution remains behind the credentialed runner ports and the organization-owned external systems.

A GitHub-hosted runner, a repository fixture, or a CI environment cannot self-issue sandbox or evaluator authority.

## Required mounted receipts

- `sealed_bank.json`
- `sandbox_authorization.json`
- `evaluator_authority.json`
- `evaluator_trust_policy.json`
- `crowdstrike_runner_authorization.json`
- `crowdstrike_credential_binding.json`
- `google_runner_authorization.json`
- `google_credential_binding.json`
- `microsoft_runner_authorization.json`
- `microsoft_credential_binding.json`

## Truth boundary

`READY_FOR_REAL_RUNS` means only that the external evidence needed to start the real run is currently admissible. It does not mean:

- Jarvis has run the sealed bank;
- CrowdStrike, Google or Microsoft has run the bank;
- blind scoring has occurred;
- Jarvis has won;
- Jarvis is production-security superior.

Those claims remain false until the existing immutable run-receipt and blind-evaluator chain contains all four real common-harness runs.

## Safety invariants

- defensive/read-only competition only;
- zero production mutation authority;
- zero exploit execution authority;
- zero credential capture authority;
- zero ground-truth visibility to runners;
- no raw credentials, private keys or sealed answers in Git, CI logs or admission receipts;
- no automatic production model/policy promotion from competition results;
- any remediation must re-race on a fresh sealed rotation.
