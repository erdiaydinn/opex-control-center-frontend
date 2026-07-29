
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path
from typing import Any, Dict, List

SCAN_FILE = Path("data/security_scan_latest.json")

def _summarize(vulns: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in vulns:
        sev = str(v.get("severity") or "medium").lower()
        if sev not in summary: sev = "medium"
        summary[sev] += 1
    return summary

def normalize_osv(raw: Dict[str, Any]) -> Dict[str, Any]:
    vulns: List[Dict[str, Any]] = []
    for result in raw.get("results", []):
        pkg = result.get("package", {}) or {}
        for v in result.get("vulnerabilities", []) or []:
            severity = "medium"
            for s in v.get("severity", []) or []:
                if str(s.get("score", "")).startswith("9"):
                    severity = "critical"
                elif str(s.get("score", "")).startswith(("7", "8")):
                    severity = "high"
            vulns.append({
                "package": pkg.get("name") or result.get("source", {}).get("path") or "unknown",
                "installed_version": pkg.get("version") or "unknown",
                "severity": severity.upper(),
                "fixed_version": (v.get("database_specific") or {}).get("fixed_version") or "review",
                "id": v.get("id"),
                "summary": v.get("summary"),
            })
    return {"generated_at": int(time.time()), "summary": _summarize(vulns), "vulnerabilities": vulns}

def run_osv_scan(project_root: str = ".") -> Dict[str, Any]:
    try:
        cmd = ["osv-scanner", "scan", "source", "-r", project_root, "--format", "json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        raw = json.loads(proc.stdout or "{}")
        normalized = normalize_osv(raw)
    except Exception as exc:
        normalized = {
            "generated_at": int(time.time()),
            "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "vulnerabilities": [],
            "warning": f"osv-scanner not available or scan failed: {exc}",
            "install_hint": "Install OSV scanner CLI or run this endpoint inside CI.",
        }
    SCAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCAN_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized

def latest_scan() -> Dict[str, Any]:
    if SCAN_FILE.exists():
        return json.loads(SCAN_FILE.read_text(encoding="utf-8"))
    return run_osv_scan(".")
