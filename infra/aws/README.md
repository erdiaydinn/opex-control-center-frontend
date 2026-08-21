# EAY AWS Production Foundation

This directory implements the repository-controlled infrastructure workstream for canonical Production Launch issue #192.

## Decision

- Primary region: AWS Europe (Frankfurt), `eu-central-1`.
- Edge/DNS/WAF: Cloudflare.
- Compute: ECS/Fargate.
- Relational data: RDS PostgreSQL, private and Multi-AZ.
- Cache/locks/queues: managed Valkey/Redis-compatible ElastiCache, private and Multi-AZ.
- Evidence/documents: private S3 with SSE-KMS, versioning and Object-Lock capability.
- Secrets: Secrets Manager + KMS. Application secret values are intentionally not committed or populated by Terraform.
- Machine access: GitHub OIDC with short-lived STS sessions; no long-lived AWS keys in the repository.
- Human administration during the AWS Free Plan phase: the MFA-protected `eay-admin` IAM administrator. AWS Organizations / IAM Identity Center is deliberately not enabled while preserving the Free Plan. A later paid/organizational phase can migrate human access to centralized SSO.

Oracle Cloud Free Trial is not a dependency of this architecture. It can remain a separate lab/fallback path while the AWS production line progresses.

## What this first infrastructure slice defines

The Terraform root under `terraform/` defines the production foundation:

1. Two-AZ VPC with separate edge, application and isolated data subnets.
2. Per-AZ NAT gateways for production availability.
3. Restrictive security groups; RDS and Valkey are never public.
4. KMS key with rotation.
5. RDS PostgreSQL with AWS-managed bootstrap secret, encryption, PITR backups and deletion protection.
6. Managed encrypted Valkey/Redis replication group with generated auth token stored in Secrets Manager.
7. Private versioned S3 evidence and backup buckets; the evidence bucket is Object-Lock capable from creation.
8. Immutable/scanned ECR repositories for EAY services.
9. ECS/Fargate cluster and private service-discovery namespace.
10. Public ALB whose security group is closed until authoritative edge CIDRs are supplied. The HTTPS listener is not created without a validated ACM certificate; when created in this foundation phase it returns a fail-closed 503 HOLD response rather than exposing an unverified workload.
11. Encrypted CloudWatch logs, infrastructure dashboard and alert topic.

Repository definition is not cloud activation. NAT, RDS, Valkey, ECS, ALB, KMS and application buckets remain unapplied until the later production activation gates authorize them.

## Current bootstrap boundaries

Three trust boundaries are intentionally separate:

1. **OIDC identity proof** — `eay-github-infra-bootstrap` trusts only `erdiaydinn/opex-control-center-frontend` on `infra/eay-production-launch-v1`. The proof workflow must show the expected AWS account/role and confirm that S3 access is denied. This role has no AWS service authority.
2. **Terraform state bootstrap** — `bootstrap/state-backend.yaml` creates only the retained, versioned, private S3 state bucket. The one-time bootstrap runs under the MFA-protected human administrator session; it does not use the zero-authority OIDC proof role.
3. **Future plan/apply authority** — separate least-privilege roles will be introduced after the state backend exists. Production `apply` authority is not granted by this slice.

## Required external inputs before an application AWS apply

The repository can be validated without cloud credentials. An application infrastructure apply requires:

- the AWS account in `eu-central-1`;
- remote state created and independently verified;
- a dedicated short-lived OIDC Terraform role with explicit least privilege;
- two globally unique application S3 bucket names;
- current Cloudflare edge ranges when origin access is opened;
- a validated ACM origin certificate when the HTTPS listener is enabled;
- exact-head CI, security and issue #192 activation gates to be GREEN.

Do not place any access key, secret key, private key, database password, OIDC client secret or Terraform state file in Git.

## Validation

```bash
cd infra/aws/terraform
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate
```

The pull-request workflow `.github/workflows/eay-production-infra-ci.yml` performs these checks on the literal PR head SHA and rejects common committed AWS credential patterns. `.github/workflows/eay-aws-state-bootstrap-ci.yml` separately gates the state bootstrap contract.

## Remote state

The production root uses the repository-owned S3 backend coordinates:

- bucket: `eay-tfstate-600219017658-eu-central-1`
- key: `eay/production/platform.tfstate`
- region: `eu-central-1`
- encryption: enabled
- locking: native S3 lockfile via `use_lockfile = true`

No DynamoDB lock table is used. The bootstrap bucket is versioned, private, TLS-only, retained across CloudFormation deletion and encrypted with S3-managed AES256 encryption. This keeps the bootstrap minimal and avoids a customer-managed KMS key before the application platform is activated.

The one-time creation and verification procedure is documented under `bootstrap/README.md`. The future automation state policy grants delete authority only to the `.tflock` object, never to the Terraform state object itself.

## Activation invariant

A successful `terraform validate`, OIDC identity proof or state-bucket bootstrap is control-plane evidence, not production acceptance. Production activation remains blocked until issue #192's staging, security, backup/restore, identity, edge, exact-release, database, load and controlled-rollout gates are independently GREEN.
