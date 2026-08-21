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
- Human/cloud administration: must use organization-controlled SSO/IAM roles; no long-lived AWS keys in the repository.

Oracle Cloud Free Trial is not a dependency of this architecture. It can remain a separate lab/fallback path while the AWS production line progresses.

## What this first infrastructure slice creates

The Terraform root under `terraform/` provisions the production foundation only:

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

This slice deliberately does **not** claim that production is live. ECS task definitions/services, exact SHA-to-image-digest admission, migration job, Cloudflare DNS/WAF, OIDC authority, populated secrets, production database role acceptance, load/failover rehearsals and controlled rollout remain later activation gates.

## Required external inputs before an AWS apply

The repository can be validated without cloud credentials. An actual apply requires:

- organization-controlled AWS account in `eu-central-1`;
- administrator/deployment access through SSO or short-lived role credentials;
- two globally unique S3 bucket names;
- a remote Terraform state backend created in a separate trust boundary;
- current Cloudflare edge ranges when origin access is opened;
- validated ACM origin certificate when the HTTPS listener is enabled.

Do not place any access key, secret key, private key, database password, OIDC client secret or Terraform state file in Git.

## Validation

```bash
cd infra/aws/terraform
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate
```

The pull-request workflow `.github/workflows/eay-production-infra-ci.yml` performs these checks on the literal PR head SHA and also rejects common committed AWS credential patterns.

## Remote state

`terraform/backend.tf` declares an S3 backend without embedded coordinates. Backend coordinates must be supplied during initialization from the deployment environment, not committed as secret-bearing local state.

Example shape only:

```bash
terraform init \
  -backend-config="bucket=<organization-controlled-state-bucket>" \
  -backend-config="key=eay/production/terraform.tfstate" \
  -backend-config="region=eu-central-1" \
  -backend-config="encrypt=true"
```

State bootstrap, state-bucket policy, versioning and independent recovery are a separate production-control step and must be completed before the first real apply.

## Activation invariant

A successful `terraform validate` is repository evidence, not production acceptance. Production activation remains blocked until issue #192's staging, security, backup/restore, identity, edge, exact-release and controlled rollout gates are independently GREEN.
