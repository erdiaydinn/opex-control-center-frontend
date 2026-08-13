"""Export hash-chained audit records to an S3 Object Lock bucket."""

from datetime import UTC, datetime, timedelta
import json
import os

import boto3

from . import persistence


def run() -> str:
    bucket = os.environ["WORKFORCE_WORM_BUCKET"]
    retention_days = int(os.getenv("WORKFORCE_WORM_RETENTION_DAYS", "3650"))
    records = persistence.list_audit(100_000) or []
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    key = f"workforce-audit/{day}/{datetime.now(UTC).strftime('%H%M%S')}.jsonl"
    body = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) for record in reversed(records)).encode()
    client = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/x-ndjson",
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=datetime.now(UTC) + timedelta(days=retention_days),
        ServerSideEncryption=os.getenv("WORKFORCE_WORM_SSE", "AES256"),
        Metadata={"record-count": str(len(records)), "source": "opex-workforce"},
    )
    return key


if __name__ == "__main__":
    print(run())
