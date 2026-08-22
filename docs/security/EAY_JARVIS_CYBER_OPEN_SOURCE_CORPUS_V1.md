# EAY Jarvis Cyber Open Source Corpus v1

## Purpose

Jarvis may learn defensive concepts, attacker behavior, detection methods, incident-response techniques, secure-design guidance and authorized adversarial evaluation patterns from public cyber-security repositories without allowing public content to create EAY company truth or attack authority.

## Trust classes

- `L0` — authoritative defensive sources such as standards, government vulnerability authorities and canonical vendor advisories. These live authorities remain governed by the existing Cyber Defense School source policy.
- `L1` — curated defensive engineering, detection, threat-intelligence, cloud, supply-chain and AppSec sources.
- `L2` — educational labs and curricula.
- `L3` — adversarial knowledge and security testing methodologies. Knowledge may be used defensively, but source tools do not become normal-chat execution authority.
- `L4` — restricted adversarial corpora containing payloads, attack validation or adversary-emulation material. Raw content is excluded from normal RAG and executable use is permitted only through the existing signed, authorized, isolated cyber sandbox.

## Initial corpus

The registry includes the seven requested repositories and a curated expansion across:

- Detection and threat hunting: SigmaHQ, signature-base, Suricata, Zeek, osquery, Velociraptor.
- Threat intelligence: MISP and OpenCTI.
- ATT&CK validation: Atomic Red Team and MITRE CALDERA.
- Cloud/container/runtime: Falco, Trivy, Prowler, Kubescape and Tetragon.
- Software supply chain: Syft, Grype, Cosign, SLSA and OSV-Scanner.
- AppSec: Semgrep, CodeQL, OWASP ZAP, DefectDojo, Dependency-Track, Nuclei, Nuclei templates and OWASP Cheat Sheet Series.
- AI/agent security: NVIDIA garak, Microsoft/Azure PyRIT, promptfoo and PurpleLlama.

The registry is intentionally curated rather than recursively importing every link from an `awesome-*` list.

## Provenance and ingestion

Knowledge ingestion and source discovery are different authorities. Every actual snapshot used for RAG/evaluation/training curriculum must be bound to:

`source_id + exact owner/repository + exact commit SHA + content fingerprint + observed archive state + license review + provenance review + security review`

A branch name such as `main` or `master` is discovery input only. Evidence and benchmark snapshots require an immutable commit SHA.

Meta-index sources may discover candidates but `auto_trust_linked_sources=false` is invariant. A newly discovered repository enters quarantine until separately reviewed.

## License boundary

Third-party source code is **not** copied into EAY product code by this corpus. `allow_code_reuse=false` is the default and current registry invariant. Copyleft, custom, unknown or content-specific licenses require explicit legal/license review before any future reuse decision. Knowledge abstraction, citation, sandbox evaluation and product-code reuse are treated as separate decisions.

## Restricted adversarial material

PayloadsAllTheThings, Atomic Red Team, CALDERA and Nuclei templates are `L4`. They are useful because a defender must understand realistic adversary behavior and validate controls, but they cannot be invoked from the normal Jarvis chat/tool path.

L4 admission requires the existing Security Guardian authorized sandbox. Production targeting, unrestricted networking, credential capture, destructive execution and company-truth promotion remain forbidden.

AI red-team frameworks such as garak, PyRIT and promptfoo are `L3` and sandbox-gated when executed. Their own execution/runtime assumptions do not override EAY isolation, scoped credentials or network policy.

## Current-state truth

A public repository may support a statement about its own current reviewed content only when a fresh immutable snapshot exists. It never proves:

- that EAY is vulnerable;
- that a CVE applies to EAY;
- that an incident occurred;
- that a detection is deployed in EAY;
- that a control works in production.

Those claims continue to require EAY-scoped evidence.

Archived sources, including `sundowndev/hacker-roadmap`, are curriculum/history only and cannot support current cyber-security truth.

## Safety invariant

> Jarvis may learn how attacks work so it can recognize, prevent, detect, contain and recover from them. External cyber knowledge never grants Jarvis permission to attack.

The corpus therefore feeds defensive reasoning, secure-code review, detection engineering, threat modeling, sandbox evaluation and benchmark design while preserving `execution_authority_granted=false` and `production_execution_allowed=false`.
