# EAY GitHub Main Protection Policy v1

## Purpose

`main` is a release authority and must not be treated as an ordinary development branch. Repository CI is only meaningful if a change cannot bypass the exact-head security gates that were used to accept it.

## Required repository rules for `main`

The GitHub ruleset / branch-protection configuration for `main` must enforce all of the following:

1. **Pull request required before merge.** Direct development pushes to `main` are prohibited.
2. **Required status checks must pass on the current head.** At minimum the EAY pre-pentest gate and applicable Platform Core/release gates must be required.
3. **Branch must be up to date before merge.** Stale-head CI must not authorize a merge after `main` moves.
4. **Conversation/review threads resolved.** Unresolved security review threads block merge.
5. **Force pushes prohibited.** No history rewrite on `main`.
6. **Branch deletion prohibited.** `main` cannot be deleted through routine repository operations.
7. **CODEOWNERS review for security-sensitive paths.** Security workflow, Workforce/Hiring authority code, migrations and security documentation require the security owner review policy configured for the repository.
8. **Administrator bypass is exceptional only.** If GitHub permits an emergency bypass, it must be treated as an incident/change-management event and documented; it must not be the normal release path.

## Required security status surface

The main-bound release path must include the current equivalent of:

- `EAY Pre-Pentest Security Acceptance`
- `Platform Core CI`
- the applicable module/release acceptance workflows surfaced by the exact candidate head
- `EAY Staging Pentest Readiness / Staging pentest fail-closed contract` when staging-security tooling or policy changes

Do not hard-code an obsolete historical run or SHA as authority. The current PR head and current `main` ancestry are authoritative.

## Staging-security environment

Create a protected GitHub Environment named `staging-security` and configure these secrets:

- `EAY_PENTEST_ALLOWED_HOSTS`: comma-separated **exact** authorized non-production DNS hostnames.
- `EAY_PRODUCTION_HOSTS`: comma-separated production DNS hostnames that must always be refused by the repository scanner.
- `EAY_PENTEST_AUTHORIZATION_ID`: the current written staging security authorization/scope identifier.

Environment protection should require an authorized reviewer before a staging scan job can begin. Secrets must not contain real application user passwords, TC numbers, candidate documents or reusable production credentials.

## Evidence rule

Changing this document, CODEOWNERS, a security workflow, the pre-pentest harness, or the target authorization guard requires fresh exact-head CI. The repository may prove that the policy contract exists and the harness is fail-closed; only GitHub repository settings can prove that the server-side branch/ruleset configuration is actually enabled.

## Current truth boundary

This policy file is configuration-as-policy, not proof that GitHub server-side branch protection is enabled. Production acceptance requires separate evidence from the live repository settings/ruleset.
