from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from app.repository_intelligence import should_index_repository_path


class RepositoryContractExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedRepositoryFacts:
    symbols: tuple[str, ...]
    contracts: tuple[str, ...]


_SQL_CONTRACT_PATTERNS = (
    (re.compile(r"\bCREATE\s+TABLE\s+([`\w.]+)", re.IGNORECASE), "sql:create-table:"),
    (re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([`\w.]+)", re.IGNORECASE), "sql:create-view:"),
    (re.compile(r"\bALTER\s+TABLE\s+([`\w.]+)", re.IGNORECASE), "sql:alter-table:"),
)
_ROUTE_PATTERN = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_ENV_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def _dedupe_sorted(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _extract_python(source: str) -> ExtractedRepositoryFacts:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise RepositoryContractExtractionError("python source could not be parsed") from exc

    symbols: list[str] = []
    contracts: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(target.id)

    for method, route in _ROUTE_PATTERN.findall(source):
        contracts.append(f"http:{method.upper()}:{route}")

    for match in _ENV_PATTERN.findall(source):
        if match.startswith(("EAY_", "OPEX_")):
            contracts.append(f"config:{match}")

    return ExtractedRepositoryFacts(_dedupe_sorted(symbols), _dedupe_sorted(contracts))


def _extract_sql(source: str) -> ExtractedRepositoryFacts:
    contracts: list[str] = []
    for pattern, prefix in _SQL_CONTRACT_PATTERNS:
        for match in pattern.findall(source):
            contracts.append(prefix + match.strip("`"))
    return ExtractedRepositoryFacts((), _dedupe_sorted(contracts))


def _extract_yaml(source: str) -> ExtractedRepositoryFacts:
    contracts: list[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        # GitHub Actions steps are usually YAML sequence items ("- uses:" / "- run:").
        # Remove only the structural list marker; never persist the run command body.
        if line.startswith("- "):
            line = line[2:].lstrip()
        if line.startswith("name:"):
            contracts.append("workflow:name:" + line.split(":", 1)[1].strip().strip("'\""))
        elif line.startswith("uses:"):
            contracts.append("workflow:uses:" + line.split(":", 1)[1].strip().strip("'\""))
        elif line.startswith("run:"):
            contracts.append("workflow:run-step")
    return ExtractedRepositoryFacts((), _dedupe_sorted(contracts))


def extract_repository_facts(path: str, source: str) -> ExtractedRepositoryFacts:
    """Extract safe structural facts only; never retain raw source text or secret values."""
    if not should_index_repository_path(path):
        raise RepositoryContractExtractionError("path is excluded from repository learning")
    if "\x00" in source:
        raise RepositoryContractExtractionError("binary-like content is not supported")

    lowered = path.lower()
    if lowered.endswith(".py"):
        return _extract_python(source)
    if lowered.endswith((".sql", ".ddl")):
        return _extract_sql(source)
    if lowered.endswith((".yml", ".yaml")):
        return _extract_yaml(source)
    return ExtractedRepositoryFacts((), ())
