# EAY Jarvis Cyber Open Source Registry v1

## Purpose

Jarvis may learn from high-value public defensive-security projects, but discovery is not installation and open source is not automatically trusted. Every upstream project is classified by defensive value, dual-use risk and the maximum environment in which EAY may consume it.

Canonical contract: `eay-cyber-open-source-registry-v1`.

## Safety invariant

> Jarvis may learn attacker behavior to defend EAY; it does not gain offensive or production-mutation authority.

No registry entry grants:

- production execution or mutation;
- credential access or validation;
- unrestricted network access;
- offensive execution;
- automatic vendoring of upstream content;
- authority to conclude that EAY is exposed or compromised.

## Admission modes

### `reference_only`

Architecture, documentation and defensive patterns may be referenced. No executable ingestion is implied.

### `read_only_corpus`

Detection or defensive content may be ingested only after:

1. immutable 40-hex upstream commit pin;
2. license review;
3. security review.

### `ci_isolated`

A defensive scanner or analyzer may be evaluated only after the read-only gates plus an isolated runner verification. Admission still does not grant production authority.

### `authorized_sandbox_only`

Active-validation or dual-use projects require all previous controls plus explicit Security Guardian sandbox authority. Targets must be allowlisted test assets; production targets, credential capture and unrestricted egress remain forbidden.

## Current high-value source families

### Detection engineering / telemetry

- SigmaHQ/sigma and pySigma
- Wazuh
- Velociraptor
- Zeek
- Suricata
- osquery
- YARA
- Falco
- Tetragon
- OpenCTI and MISP

### DFIR

- Volatility 3
- Timesketch
- Plaso
- Hayabusa
- Chainsaw

### AppSec and software supply chain

- Semgrep
- OWASP ZAP
- Trivy
- OSV-Scanner
- Syft and Grype
- Sigstore Cosign
- in-toto
- OpenSSF Scorecard and Allstar
- Gitleaks and TruffleHog

### Kubernetes / cloud policy

- Kyverno
- OPA Gatekeeper
- Kubescape

### AI / agentic security

- NVIDIA garak
- Microsoft PyRIT
- promptfoo
- NVIDIA NeMo Guardrails

### Dual-use defensive validation

The following are deliberately sandbox-only:

- MITRE CALDERA
- Atomic Red Team
- ProjectDiscovery Nuclei
- Nuclei Templates

They are useful for understanding and validating defenses, not for giving Jarvis attack authority.

## Upstream trust is not transitive

Security projects can themselves ship vulnerabilities or suffer supply-chain compromise. EAY therefore does not execute `latest`, floating tags, unaudited installers or arbitrary upstream workflows. Every executable candidate must be pinned to a reviewed immutable commit/release and run in an isolated environment with least privilege and bounded network access.

## Truth boundary

This registry means the projects are **governed candidates** for Jarvis defensive learning and validation. It does not mean their code has been vendored, their licenses have been approved, their current releases have passed EAY security review, or their tools are active in production. Those claims require separate exact-version evidence.
