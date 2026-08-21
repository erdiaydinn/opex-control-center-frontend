#!/usr/bin/env python3
"""Observe known dependency vulnerabilities through the official OSV API.

The observer consumes only versioned Package URLs already present in a CycloneDX
BOM. It records an input digest, observation time, source state and package-level
OSV identifiers. An unavailable/invalid upstream is never converted to a zero-
finding result. This is observation evidence only: it does not establish code
reachability, exploitability, production deployment, or remediation authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OSV_QUERY_BATCH_URL = "https://api.osv.dev/v1/querybatch"
DEFAULT_BATCH_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 20.0


class ObservationUnavailable(RuntimeError):
    """Raised when OSV cannot produce a trustworthy observation."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_versioned_purls(sbom: dict[str, Any]) -> list[str]:
    if sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("input must be a CycloneDX BOM")

    purls: set[str] = set()
    for component in sbom.get("components") or []:
        if not isinstance(component, dict):
            continue
        purl = component.get("purl")
        version = component.get("version")
        if not isinstance(purl, str) or not purl.startswith("pkg:"):
            continue
        if not isinstance(version, str) or not version:
            continue
        if "@" not in purl.rsplit("?", maxsplit=1)[0]:
            continue
        purls.add(purl)

    if not purls:
        raise ValueError("CycloneDX BOM contains no versioned package URLs to observe")
    return sorted(purls)


def post_query_batch(queries: list[dict[str, Any]], timeout: float) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        OSV_QUERY_BATCH_URL,
        data=json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "EAY-Security-Guardian-OSV-Observer/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ObservationUnavailable(f"unexpected_http_status_{response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ObservationUnavailable(f"http_{exc.code}") from exc
    except (
        urllib.error.URLError,
        TimeoutError,
        socket.timeout,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise ObservationUnavailable(type(exc).__name__) from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or len(results) != len(queries):
        raise ObservationUnavailable("invalid_querybatch_response_shape")
    if not all(isinstance(item, dict) for item in results):
        raise ObservationUnavailable("invalid_querybatch_result_shape")
    return results


def query_osv(purls: list[str], batch_size: int, timeout: float) -> dict[str, list[dict[str, str]]]:
    findings: dict[str, list[dict[str, str]]] = {purl: [] for purl in purls}

    for start in range(0, len(purls), batch_size):
        batch = purls[start : start + batch_size]
        pending: list[tuple[str, str | None]] = [(purl, None) for purl in batch]

        while pending:
            queries = []
            for purl, page_token in pending:
                query: dict[str, Any] = {"package": {"purl": purl}}
                if page_token:
                    query["page_token"] = page_token
                queries.append(query)

            results = post_query_batch(queries, timeout)
            next_pending: list[tuple[str, str | None]] = []
            for (purl, _), result in zip(pending, results, strict=True):
                vulns = result.get("vulns", [])
                if not isinstance(vulns, list):
                    raise ObservationUnavailable("invalid_vulnerability_list")
                for vuln in vulns:
                    if not isinstance(vuln, dict):
                        raise ObservationUnavailable("invalid_vulnerability_record")
                    vuln_id = vuln.get("id")
                    modified = vuln.get("modified")
                    if not isinstance(vuln_id, str) or not vuln_id:
                        raise ObservationUnavailable("vulnerability_id_missing")
                    findings[purl].append(
                        {
                            "id": vuln_id,
                            "modified": modified if isinstance(modified, str) else "unknown",
                        }
                    )

                next_page_token = result.get("next_page_token")
                if next_page_token is not None:
                    if not isinstance(next_page_token, str) or not next_page_token:
                        raise ObservationUnavailable("invalid_next_page_token")
                    next_pending.append((purl, next_page_token))
            pending = next_pending

    for purl, records in findings.items():
        unique = {(item["id"], item["modified"]): item for item in records}
        findings[purl] = [unique[key] for key in sorted(unique)]
    return findings


def observed_payload(
    *,
    input_path: Path,
    input_digest: str,
    purls: list[str],
    findings: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    vulnerable = {purl: records for purl, records in findings.items() if records}
    unique_ids = sorted(
        {
            record["id"]
            for records in vulnerable.values()
            for record in records
        }
    )
    return {
        "schema_version": 1,
        "observer": "osv.dev",
        "source_endpoint": OSV_QUERY_BATCH_URL,
        "source_state": "observed",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input": {
            "path": input_path.name,
            "sha256": input_digest,
            "versioned_purl_count": len(purls),
        },
        "summary": {
            "queried_components": len(purls),
            "vulnerable_components": len(vulnerable),
            "unique_vulnerability_ids": len(unique_ids),
            "zero_findings_claim_allowed": True,
        },
        "vulnerability_ids": unique_ids,
        "components": [
            {"purl": purl, "vulnerabilities": vulnerable[purl]}
            for purl in sorted(vulnerable)
        ],
        "truth_boundary": {
            "code_reachability_proven": False,
            "exploitability_proven": False,
            "production_deployment_attested": False,
            "automatic_remediation_authority": False,
        },
    }


def unavailable_payload(
    *,
    input_path: Path,
    input_digest: str,
    purl_count: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "observer": "osv.dev",
        "source_endpoint": OSV_QUERY_BATCH_URL,
        "source_state": "unavailable",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input": {
            "path": input_path.name,
            "sha256": input_digest,
            "versioned_purl_count": purl_count,
        },
        "summary": {
            "queried_components": None,
            "vulnerable_components": None,
            "unique_vulnerability_ids": None,
            "zero_findings_claim_allowed": False,
        },
        "vulnerability_ids": None,
        "components": None,
        "unavailable_reason_class": reason,
        "truth_boundary": {
            "code_reachability_proven": False,
            "exploitability_proven": False,
            "production_deployment_attested": False,
            "automatic_remediation_authority": False,
        },
    }


def write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--allow-unavailable",
        action="store_true",
        help="write an explicit unavailable observation instead of failing the CI job",
    )
    args = parser.parse_args()

    if not 1 <= args.batch_size <= 500:
        raise SystemExit("--batch-size must be between 1 and 500")
    if not 1.0 <= args.timeout <= 120.0:
        raise SystemExit("--timeout must be between 1 and 120 seconds")

    raw = args.sbom.read_bytes()
    digest = sha256_bytes(raw)
    try:
        document = json.loads(raw.decode("utf-8"))
        purls = load_versioned_purls(document)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit(f"invalid SBOM input: {type(exc).__name__}") from exc

    try:
        findings = query_osv(purls, args.batch_size, args.timeout)
        payload = observed_payload(
            input_path=args.sbom,
            input_digest=digest,
            purls=purls,
            findings=findings,
        )
        write_output(args.output, payload)
        print(
            "OSV dependency observation: PASS "
            f"(queried={payload['summary']['queried_components']}, "
            f"vulnerable_components={payload['summary']['vulnerable_components']}, "
            f"unique_ids={payload['summary']['unique_vulnerability_ids']}, "
            "production_runtime_proof=false)"
        )
    except ObservationUnavailable as exc:
        payload = unavailable_payload(
            input_path=args.sbom,
            input_digest=digest,
            purl_count=len(purls),
            reason=str(exc) or type(exc).__name__,
        )
        write_output(args.output, payload)
        print(
            "OSV dependency observation: UNAVAILABLE "
            "(zero_findings_claim_allowed=false, production_runtime_proof=false)"
        )
        if not args.allow_unavailable:
            raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
