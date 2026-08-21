#!/usr/bin/env python3
"""Bounded, non-destructive black-box security probe for authorized EAY staging.

This is deliberately not a general-purpose exploitation tool. It probes only a
small EAY-owned surface, never follows redirects, never brute-forces, and never
mutates business data. Active mode adds TRACE and traversal-resistance checks.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SEVERITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
PROTECTED_PATHS = (
    "/api/workforce/admin/bootstrap",
    "/api/workforce/people",
    "/api/recruitment/bootstrap",
    "/api/recruitment/hr-actual/latest",
)
SENSITIVE_PATHS = (
    "/.env",
    "/.git/config",
    "/server-status",
    "/actuator/env",
)
SECRET_MARKERS = (
    "database_url",
    "aws_secret",
    "client_secret",
    "password=",
    "secret=",
    "token=",
    "[core]",
    "jdbc:",
    "private key",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass
class Finding:
    severity: str
    check: str
    detail: str
    path: str = "/"


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: str


def _origin(target_url: str) -> str:
    parsed = urlsplit(target_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _url(origin: str, path: str) -> str:
    if not path.startswith("/"):
        raise ValueError("probe path must be absolute")
    return f"{origin}{path}"


def _request(origin: str, path: str, *, method: str = "GET", headers: dict[str, str] | None = None) -> HttpResult:
    request = Request(
        _url(origin, path),
        method=method,
        headers={"User-Agent": "EAY-Authorized-Staging-Security-Probe/1.0", **(headers or {})},
    )
    opener = build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=8)
        raw = response.read(65536)
        return HttpResult(response.status, {k.lower(): v for k, v in response.headers.items()}, raw.decode("utf-8", "replace"))
    except HTTPError as error:
        raw = error.read(65536)
        return HttpResult(error.code, {k.lower(): v for k, v in error.headers.items()}, raw.decode("utf-8", "replace"))
    except (URLError, TimeoutError, ssl.SSLError) as error:
        raise RuntimeError(f"network probe failed for {path}: {type(error).__name__}") from error


def _security_headers(result: HttpResult) -> list[Finding]:
    findings: list[Finding] = []
    required = {
        "strict-transport-security": "HSTS header is missing at the external HTTPS boundary.",
        "x-content-type-options": "X-Content-Type-Options is missing.",
        "referrer-policy": "Referrer-Policy is missing.",
    }
    for header, detail in required.items():
        if not result.headers.get(header):
            findings.append(Finding("medium", "security-header", detail))
    if not (result.headers.get("content-security-policy") or result.headers.get("x-frame-options")):
        findings.append(Finding("medium", "clickjacking-boundary", "Neither CSP frame-ancestors nor X-Frame-Options is present."))
    return findings


def _cors_probe(origin: str) -> list[Finding]:
    path = PROTECTED_PATHS[0]
    result = _request(
        origin,
        path,
        method="OPTIONS",
        headers={
            "Origin": "https://attacker.invalid",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    allow_origin = result.headers.get("access-control-allow-origin", "").strip().lower()
    credentials = result.headers.get("access-control-allow-credentials", "").strip().lower() == "true"
    if allow_origin == "https://attacker.invalid" and credentials:
        return [Finding("critical", "cors", "Protected API reflects an attacker origin while credentials are allowed.", path)]
    if allow_origin == "*" and credentials:
        return [Finding("critical", "cors", "Protected API combines wildcard CORS with credential allowance.", path)]
    if allow_origin in {"*", "https://attacker.invalid"}:
        return [Finding("high", "cors", "Protected API accepts an untrusted cross-origin caller.", path)]
    return []


def _protected_api_probe(origin: str) -> list[Finding]:
    findings: list[Finding] = []
    spoofed = {
        "Authorization": "Bearer eay-pentest-invalid-token",
        "X-OPEX-User": "attacker@invalid",
        "X-OPEX-Role": "super_admin",
        "X-OPEX-Permissions": "viewWorkforce,viewPeople,viewRecruitment,manageRecruitmentActuals",
    }
    for path in PROTECTED_PATHS:
        anonymous = _request(origin, path)
        if 200 <= anonymous.status < 300:
            findings.append(Finding("critical", "anonymous-authorization", f"Protected endpoint returned {anonymous.status} without credentials.", path))
        elif anonymous.status >= 500:
            findings.append(Finding("high", "anonymous-authorization", f"Protected endpoint failed with server error {anonymous.status} instead of rejecting access.", path))
        elif anonymous.status == 404:
            findings.append(Finding("high", "release-parity", "Expected protected endpoint is missing from staging; release parity cannot be proven.", path))

        forged = _request(origin, path, headers=spoofed)
        if 200 <= forged.status < 300:
            findings.append(Finding("critical", "header-impersonation", f"Forged browser role/permission headers bypassed protection with status {forged.status}.", path))
        elif forged.status >= 500:
            findings.append(Finding("high", "header-impersonation", f"Forged identity produced server error {forged.status} instead of a controlled rejection.", path))
    return findings


def _sensitive_file_probe(origin: str) -> list[Finding]:
    findings: list[Finding] = []
    for path in SENSITIVE_PATHS:
        result = _request(origin, path)
        if 200 <= result.status < 300:
            body = result.body.lower()
            marker = next((value for value in SECRET_MARKERS if value in body), None)
            severity = "critical" if marker else "high"
            detail = "Potential secret/configuration content is publicly readable." if marker else "Sensitive infrastructure path returned a successful response."
            findings.append(Finding(severity, "sensitive-file-exposure", detail, path))
    return findings


def _production_docs_probe(origin: str) -> list[Finding]:
    findings: list[Finding] = []
    for path in ("/api/docs", "/api/openapi.json"):
        result = _request(origin, path)
        if 200 <= result.status < 300:
            findings.append(Finding("medium", "production-docs", "Interactive API documentation/schema is exposed on the staging production-shaped boundary.", path))
    return findings


def _active_probe(origin: str) -> list[Finding]:
    findings: list[Finding] = []
    trace = _request(origin, "/", method="TRACE")
    if 200 <= trace.status < 300:
        findings.append(Finding("high", "http-trace", "TRACE is enabled at the external boundary."))

    traversal_path = "/..%2f..%2f..%2fetc%2fpasswd"
    traversal = _request(origin, traversal_path)
    if 200 <= traversal.status < 300 and "root:x:0:0" in traversal.body.lower():
        findings.append(Finding("critical", "path-traversal", "Traversal probe returned a Unix passwd marker.", traversal_path))
    return findings


def run_probe(target_url: str, mode: str) -> dict:
    origin = _origin(target_url)
    root = _request(origin, "/")
    findings = _security_headers(root)
    findings.extend(_cors_probe(origin))
    findings.extend(_protected_api_probe(origin))
    findings.extend(_sensitive_file_probe(origin))
    findings.extend(_production_docs_probe(origin))
    if mode == "active":
        findings.extend(_active_probe(origin))

    counts = {severity: sum(1 for item in findings if item.severity == severity) for severity in SEVERITY}
    return {
        "schema_version": 1,
        "target_origin": origin,
        "mode": mode,
        "request_policy": "bounded-non-destructive-no-redirect-no-bruteforce",
        "counts": counts,
        "findings": [asdict(item) for item in findings],
    }


def _self_test() -> None:
    headers = HttpResult(200, {"x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}, "")
    assert any(item.check == "security-header" for item in _security_headers(headers))
    assert _origin("https://staging.example/path?q=1") == "https://staging.example"
    assert SEVERITY["critical"] > SEVERITY["high"] > SEVERITY["medium"]
    print("EAY staging black-box probe self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-url")
    parser.add_argument("--mode", choices=("baseline", "active"), default="baseline")
    parser.add_argument("--report", default="build/security/eay-staging-blackbox.json")
    parser.add_argument("--fail-level", choices=("medium", "high", "critical"), default="high")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if not args.target_url:
        parser.error("--target-url is required unless --self-test is used")

    report = run_probe(args.target_url, args.mode)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    threshold = SEVERITY[args.fail_level]
    blocking = [item for item in report["findings"] if SEVERITY[item["severity"]] >= threshold]
    print(json.dumps(report["counts"], sort_keys=True))
    if blocking:
        print(f"BLOCKED: {len(blocking)} finding(s) at or above {args.fail_level}", file=sys.stderr)
        return 3
    print("EAY authorized staging black-box probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
