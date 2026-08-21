# EAY AWS Bootstrap Trust Boundary

This directory owns the small, one-time AWS control-plane bootstrap that must exist before the production Terraform root can use remote state.

## Free-plan invariant

The bootstrap must not create or join AWS Organizations, enable Control Tower, or require a paid-plan-only service. It creates only one S3 bucket in `eu-central-1` through a CloudFormation stack. The bucket is retained if the stack is deleted, private, versioned, BucketOwnerEnforced, TLS-only and encrypted with S3-managed AES256 encryption. A customer-managed KMS key is deliberately not used for Terraform state during this free-plan bootstrap, avoiding a standing KMS-key dependency and cost.

No NAT Gateway, RDS, ECS/Fargate, ElastiCache, ALB, KMS key or application workload is created here.

## Why S3 lockfiles, not DynamoDB

Terraform 1.10.5 supports the S3 backend `use_lockfile = true` contract. The production root therefore uses an S3 lock object beside the state object and does not create a DynamoDB locking table.

State coordinates:

- bucket: `eay-tfstate-600219017658-eu-central-1`
- region: `eu-central-1`
- state key: `eay/production/platform.tfstate`
- lock key: `eay/production/platform.tfstate.tflock`

The state object can be read and updated but is intentionally not granted `s3:DeleteObject` in the least-privilege automation policy. Only the `.tflock` object receives delete authority because Terraform must release the lock.

## Bootstrap authority

The existing GitHub role `eay-github-infra-bootstrap` remains an identity-proof role with no AWS service permissions. Do not attach the state-access policy to that role. The state bucket is a separate trust boundary and is created once under the MFA-protected human administrator session.

After the bucket exists, create a separate future automation role for Terraform state/plan access and attach only `terraform-state-access-policy.json` plus the minimum read authorities required for planning. Production apply authority remains a different, later gate.

## One-time creation

From an AWS CloudShell session opened while signed in as the MFA-protected `eay-admin` account, run the repository-controlled script:

```bash
curl -fsSL https://raw.githubusercontent.com/erdiaydinn/opex-control-center-frontend/infra/eay-production-launch-v1/infra/aws/bootstrap/cloudshell-create-state.sh | bash
```

The script first proves the AWS account ID, then deploys the CloudFormation template and verifies versioning, encryption, public-access blocking and bucket-policy status. It does not upgrade the account plan.

## Recovery rules

- The S3 bucket has CloudFormation `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.
- Bucket versioning is mandatory; old state versions are intentionally not lifecycle-deleted by this bootstrap.
- Never force-push Terraform state unless a documented recovery procedure has first pulled and preserved the current remote state.
- Never commit `.terraform/`, `*.tfstate`, `*.tfstate.*`, AWS access keys or generated backend credentials.

## Exact-head evidence

Changes under `infra/aws/**` trigger both the production infrastructure validation and the branch-scoped OIDC identity proof. The OIDC workflow binds the STS role-session name to the literal GitHub SHA, verifies that exact assumed-role ARN, and updates a single evidence marker on PR #210 with the commit SHA, AWS caller ARN, denied S3 authority and an evidence SHA-256 digest. This keeps repository validation and cloud-identity proof bound to the same infrastructure head and makes the same SHA visible in AWS CloudTrail.

## Promotion gate

Creating the state bucket is not permission to run the production stack. Before any `terraform plan` or `apply` against AWS, the OIDC identity proof, exact-head infrastructure CI, state-access role, budget guards and the relevant issue #192 activation gates must be independently GREEN.
