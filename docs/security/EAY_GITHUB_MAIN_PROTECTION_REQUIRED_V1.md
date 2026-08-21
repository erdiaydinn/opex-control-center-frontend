# EAY Main Protection Required Settings v1

`main` is currently expected to be a protected release branch. Repository CI can detect unsafe lineage, but GitHub branch/ruleset protection is the control that prevents an unsafe write before it lands.

## Minimum required repository setting

Apply a GitHub branch protection rule or repository ruleset to `main` with:

- require a pull request before merge;
- require status checks to pass before merge;
- require the branch to be up to date before merge;
- require conversation resolution before merge;
- block force pushes;
- block branch deletion;
- do not allow bypass for routine administrator merges;
- require signed commits when operationally compatible with the release tooling.

At minimum, select the current main-bound checks that represent:

- `EAY Pre-Pentest Security Acceptance`;
- `Platform Core CI`;
- the applicable cumulative/release acceptance workflow for the changed module.

Do not hard-code a stale workflow run or SHA as authority. Required checks must execute on the current candidate head.

## Review requirement

For the current single-maintainer operating model, mandatory independent approval can create an impossible self-approval deadlock. The minimum enforceable control is therefore PR-only + exact-head required status checks + no force/deletion/bypass.

When a second trusted security/release maintainer is available, raise the rule to:

- at least one approval;
- dismiss stale approvals on new commits;
- require CODEOWNERS review for security-sensitive paths.

## Verification evidence

After the GitHub setting is applied, attach evidence showing:

- `main` reports protected/ruleset enforced;
- direct push is rejected;
- force push is rejected;
- a PR with a RED required security check cannot merge;
- the same PR can merge only after the exact-head required checks are GREEN.

Repository documentation alone is **not** evidence that branch protection is active. The live GitHub repository setting is the authority.
