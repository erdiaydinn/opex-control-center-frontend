from __future__ import annotations

import io
import json
import re
import subprocess
import tokenize
from pathlib import Path

ROOT = Path("services/core-api")
REPORT_DIR = Path(".eay/ci")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_e501_files() -> list[Path]:
    completed = subprocess.run(
        ["ruff", "check", str(ROOT), "--output-format=json"],
        check=False,
        capture_output=True,
        text=True,
    )
    diagnostics = json.loads(completed.stdout or "[]")
    return sorted(
        {
            Path(item["filename"])
            for item in diagnostics
            if item.get("code") == "E501"
        }
    )


def safe_break_positions(line: str) -> list[int]:
    if "--" in line:
        return []
    positions: list[int] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        char = line[i]
        if char == "'" and not in_double:
            if in_single and i + 1 < len(line) and line[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            if in_double and i + 1 < len(line) and line[i + 1] == '"':
                i += 2
                continue
            in_double = not in_double
        elif char.isspace() and not in_single and not in_double:
            positions.append(i)
        i += 1
    return positions


def wrap_content_line(line: str, max_len: int = 96) -> str:
    pending = [line]
    output: list[str] = []
    while pending:
        current = pending.pop(0)
        if len(current) <= max_len:
            output.append(current)
            continue
        indent_match = re.match(r"\s*", current)
        indent = indent_match.group(0) if indent_match else ""
        positions = [
            position
            for position in safe_break_positions(current)
            if position > len(indent) + 20
        ]
        before = [position for position in positions if position <= max_len]
        split_at = max(before) if before else (min(positions) if positions else None)
        if split_at is None:
            output.append(current)
            continue
        output.append(current[:split_at].rstrip())
        pending.insert(0, indent + current[split_at:].lstrip())
    return "\n".join(output)


def process_multiline_string(raw: str) -> str:
    match = re.match(r"(?is)^([rubf]*)(\"\"\"|'{3})", raw)
    if not match:
        return raw
    quote = match.group(2)
    if not raw.endswith(quote):
        return raw
    prefix_len = len(match.group(1)) + len(quote)
    body = raw[prefix_len:-len(quote)]
    lines = body.split("\n")
    wrapped = [wrap_content_line(line) for line in lines]
    if wrapped == lines:
        return raw
    return raw[:prefix_len] + "\n".join(wrapped) + quote


def process_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    line_offsets = [0]
    line_offsets.extend(match.end() for match in re.finditer(r"\n", source))
    replacements: list[tuple[int, int, str]] = []

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING or "\n" not in token.string:
            continue
        processed = process_multiline_string(token.string)
        if processed == token.string:
            continue
        start_line, start_col = token.start
        end_line, end_col = token.end
        start = line_offsets[start_line - 1] + start_col
        end = line_offsets[end_line - 1] + end_col
        replacements.append((start, end, processed))

    for start, end, processed in reversed(replacements):
        source = source[:start] + processed + source[end:]

    if replacements:
        path.write_text(source, encoding="utf-8")
    return len(replacements)


def apply_exact_replacements() -> list[str]:
    applied: list[str] = []

    promotion = ROOT / "app/modules/field_intelligence/promotion.py"
    if promotion.exists():
        text = promotion.read_text(encoding="utf-8")
        old = (
            "    if not isinstance(sku, str) or not sku.strip():\n"
            "        sku = None\n"
            "    else:\n"
            "        sku = sku.strip()"
        )
        new = (
            "    sku = None if not isinstance(sku, str) or "
            "not sku.strip() else sku.strip()"
        )
        if old in text:
            promotion.write_text(text.replace(old, new, 1), encoding="utf-8")
            applied.append("SIM108_SKU_REPAIR")

    migration = ROOT / "alembic/versions/0019_field_intelligence_foundation.py"
    if migration.exists():
        text = migration.read_text(encoding="utf-8")
        old = (
            '            " (\'unseen\',\'seen\',\'started\',\'partial\',\'submitted\','
            '\'rework\',\'verified\',\'overdue\',\'exempt\')",'
        )
        new = (
            '            " (\'unseen\',\'seen\',\'started\',\'partial\',\'submitted\','
            '\'rework\'," \n'
            '            "\'verified\',\'overdue\',\'exempt\')",'
        )
        if old in text:
            migration.write_text(text.replace(old, new, 1), encoding="utf-8")
            applied.append("FIELD_STATUS_LITERAL_REPAIR")

    return applied


def main() -> int:
    files = load_e501_files()
    lines = [f"E501_INPUT_FILES={len(files)}"]
    changed = 0
    for path in files:
        count = process_file(path)
        if count:
            changed += 1
            lines.append(f"SQL_WRAP_FILE={path} TOKENS={count}")
    for item in apply_exact_replacements():
        lines.append(f"{item}=APPLIED")
    lines.append(f"SQL_WRAP_CHANGED_FILES={changed}")

    compile_result = subprocess.run(
        ["python", "-m", "compileall", "-q", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    lines.append(f"COMPILE_EXIT_CODE={compile_result.returncode}")
    if compile_result.stdout:
        lines.append(compile_result.stdout)
    if compile_result.stderr:
        lines.append(compile_result.stderr)

    report = "\n".join(lines) + "\n"
    (REPORT_DIR / "sql-wrap-output.txt").write_text(report, encoding="utf-8")
    print(report, end="")
    return compile_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
