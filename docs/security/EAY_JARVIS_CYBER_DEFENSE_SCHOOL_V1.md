# EAY Jarvis Cyber Defense School v1

## Purpose

Train and measure Jarvis as a defensive cyber-security specialist that recognizes broad attacker behavior while preserving strict non-offensive authority boundaries.

## Canonical composition

This workstream is stacked on `product/jarvis-general-intelligence-v1` and reuses the existing Jarvis cyber-defense, company-truth, attack-path, detection, platform-assurance and benchmark contracts. It does not create a second execution authority.

## Defense domains

The curriculum requires complete coverage across:

1. Web and API security
2. Identity and access security
3. Cloud and container security
4. Endpoint and network defense
5. Software supply chain security
6. Data security
7. Mobile and device security
8. AI and agentic security
9. Insider and social-engineering defense
10. IoT and OT defense
11. Incident response and detection engineering

## Knowledge source families

The school contract recognizes MITRE ATT&CK, MITRE D3FEND, CISA KEV, FIRST EPSS, NVD/CVE, CWE, CAPEC, OWASP ASVS, OWASP API Security, OWASP Mobile, OWASP GenAI, vendor advisories, GitHub Security Advisories, Sigma, YARA and NIST CSF.

Each source has an explicit authority class and freshness window. CISA KEV alone may assert known exploitation at the global threat layer. No public source may assert EAY/company exposure, confirm a company incident or grant execution authority.

## EAY architecture awareness

Knowledge alone is insufficient. A domain receipt is READY only when:

- all required source families are present;
- freshness policy passes;
- EAY surface references are bound;
- EAY evidence references are bound;
- unresolved questions are empty.

This prevents generic cyber knowledge from becoming a false company-specific security claim.

## Defensive-only invariant

The contract hard-fails any attempt to enable:

- exploit generation;
- destructive execution;
- credential capture;
- production mutation;
- automatic remediation;
- security execution authority.

Attack behavior references are descriptive inputs for recognition, detection, prioritization and mitigation planning only.

## Measured graduation

The school composes with the canonical `cyber_benchmark_intelligence` contract. A mentor-outperformance claim is allowed only when every defense domain is current and EAY-aware and the existing authorized-sandbox or field-read-only cyber benchmark independently allows a superiority claim.

The graduation gate never permits a `production security superiority` claim. Production acceptance remains a separate real-environment evidence process.

## External truth boundary

Repository tests prove contract behavior only. They do not prove that every external threat feed is live, every EAY production surface has been observed, or that independent production penetration/incident-response acceptance has occurred.
