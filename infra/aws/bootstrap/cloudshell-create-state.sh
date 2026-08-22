#!/usr/bin/env bash
set -euo pipefail

EXPECTED_ACCOUNT_ID="600219017658"
REGION="eu-central-1"
STACK_NAME="eay-terraform-state-bootstrap"
STATE_BUCKET="eay-tfstate-600219017658-eu-central-1"
TEMPLATE_URL="https://raw.githubusercontent.com/erdiaydinn/opex-control-center-frontend/infra/eay-production-launch-v1/infra/aws/bootstrap/state-backend.yaml"
EXPECTED_TEMPLATE_SHA256="9eb6d3b47a6e4b28ba1b22d5ff7fc4175a7697633967312242b9cd72655674d9"

actual_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${actual_account}" != "${EXPECTED_ACCOUNT_ID}" ]]; then
  echo "Refusing bootstrap: expected AWS account ${EXPECTED_ACCOUNT_ID}, got ${actual_account}." >&2
  exit 1
fi

caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
echo "AWS identity: ${caller_arn}"
echo "Target region: ${REGION}"
echo "State bucket: ${STATE_BUCKET}"

template_file="$(mktemp)"
trap 'rm -f "${template_file}" /tmp/eay-state-public-access.json' EXIT
curl --fail --silent --show-error --location "${TEMPLATE_URL}" --output "${template_file}"

actual_template_sha256="$(sha256sum "${template_file}" | awk '{print $1}')"
if [[ "${actual_template_sha256}" != "${EXPECTED_TEMPLATE_SHA256}" ]]; then
  echo "Refusing bootstrap: state template digest mismatch." >&2
  echo "Expected: ${EXPECTED_TEMPLATE_SHA256}" >&2
  echo "Actual:   ${actual_template_sha256}" >&2
  exit 1
fi

echo "State template digest verified: ${actual_template_sha256}"

aws cloudformation deploy \
  --region "${REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file "${template_file}" \
  --parameter-overrides "StateBucketName=${STATE_BUCKET}" \
  --no-fail-on-empty-changeset

versioning="$(aws s3api get-bucket-versioning --bucket "${STATE_BUCKET}" --region "${REGION}" --query Status --output text)"
if [[ "${versioning}" != "Enabled" ]]; then
  echo "State bucket versioning is not enabled." >&2
  exit 1
fi

aws s3api get-public-access-block --bucket "${STATE_BUCKET}" --region "${REGION}" >/tmp/eay-state-public-access.json
python3 - <<'PY'
import json
with open('/tmp/eay-state-public-access.json', encoding='utf-8') as fh:
    cfg = json.load(fh)['PublicAccessBlockConfiguration']
required = ('BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets')
if not all(cfg.get(k) is True for k in required):
    raise SystemExit('State bucket public-access block is incomplete.')
PY

algorithm="$(aws s3api get-bucket-encryption --bucket "${STATE_BUCKET}" --region "${REGION}" --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text)"
if [[ "${algorithm}" != "AES256" ]]; then
  echo "Unexpected state-bucket encryption algorithm: ${algorithm}" >&2
  exit 1
fi

policy_public="$(aws s3api get-bucket-policy-status --bucket "${STATE_BUCKET}" --region "${REGION}" --query 'PolicyStatus.IsPublic' --output text)"
if [[ "${policy_public}" != "False" && "${policy_public}" != "false" ]]; then
  echo "State bucket policy is public." >&2
  exit 1
fi

stack_status="$(aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK_NAME}" --query 'Stacks[0].StackStatus' --output text)"
echo "Bootstrap stack: ${stack_status}"
echo "Remote-state bootstrap verified. No Organizations, Control Tower, NAT, RDS, ECS, ElastiCache or KMS resources were created by this bootstrap."
