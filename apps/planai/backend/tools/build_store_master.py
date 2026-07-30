"""Build the Planogram store master from the approved cupboard inventory CSV.

The inventory is the source of truth for depot names and cold/frozen equipment.
The generated JSON is deterministic so it can be reviewed and versioned.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path


CHILLED_COLUMNS = {
    "Banabi +4 Dikey Adt",
    "(+)4 Martek",
    "Sütaş +4 Dikey",
    "Sütaş +4 Yatay",
    "Coca Cola +4 Dikey çift Kapı",
    "Coca Cola +4 Dikey Tek Kapı",
    "İçim +4 Dikey Adt",
    "Redbul Mini Dolap Adt",
    "Dardanel +4 Dikey",
    "Pepsi +4 Dikey",
    "Pınar +4 Dikey",
}

FROZEN_COLUMNS = {
    "Banabi Yatay -18",
    "-18 Martek",
    "Algida Donuk Yatay 800 Lt",
    "Algida Donuk Yatay 500 Lt",
    "Superfresh Donuk Yatay 400 Lt",
    "Superfresh Donuk Yatay 500 Lt",
    "Superfresh Donuk Yatay 800 Lt",
    "Pernigotti Donuk",
    "Eti Alaska Donuk",
    "La Lorreine Donuk Dikey",
    "La Lorreine Donuk Yatay",
    "Pınar -18 Yatay",
    "Pınar -18 Dikey",
    "FEAST -18",
    "Golf -18 Yatay",
}

ALIASES = {
    "Yemeksepeti Market, ": "",
}


def integer(value: object) -> int:
    try:
        return int(float(str(value or "0").strip().replace(",", ".")))
    except ValueError:
        return 0


def ascii_code(value: str) -> str:
    table = str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
        "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    normalized = unicodedata.normalize("NFKD", value.translate(table))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", "_", normalized.upper()).strip("_")


def clean_header(value: str) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def display_name(raw: str) -> str:
    value = str(raw or "").strip()
    for old, new in ALIASES.items():
        value = value.replace(old, new)
    return value


def city_from_name(name: str) -> str:
    match = re.search(r"\(([^()]+)\)\s*$", name)
    return match.group(1).strip() if match else ""


def fixture_key(header: str) -> str:
    return ascii_code(header).lower()


def build(source: Path) -> list[dict]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if len(rows) < 3:
        raise ValueError("Inventory CSV does not contain a header and depot rows.")

    headers = [clean_header(value) for value in rows[1]]
    stores: list[dict] = []
    seen: set[str] = set()
    current_region = ""

    for values in rows[2:]:
        row = {
            headers[index]: values[index].strip() if index < len(values) else ""
            for index in range(len(headers))
            if headers[index]
        }
        raw_name = row.get("Depo Adı", "")
        if not raw_name:
            continue
        if not raw_name.startswith("Yemeksepeti Market,"):
            current_region = clean_header(raw_name)
            continue

        name = display_name(raw_name)
        base_name = re.sub(r"\s*\([^()]+\)\s*$", "", name).strip()
        code = ascii_code(base_name)
        if code in seen:
            code = ascii_code(name)
        seen.add(code)

        inventory = {
            fixture_key(header): integer(row.get(header))
            for header in headers[2:]
            if header not in {"Açıklama ve Sorunlar"} and integer(row.get(header))
        }
        chilled_total = sum(integer(row.get(header)) for header in CHILLED_COLUMNS)
        frozen_total = sum(integer(row.get(header)) for header in FROZEN_COLUMNS)
        algida_count = (
            integer(row.get("Algida Donuk Yatay 800 Lt"))
            + integer(row.get("Algida Donuk Yatay 500 Lt"))
        )

        default_dna = {
            "warehouse_size": "medium",
            "aisle_count": 10 if code == "FULYA" else 8,
            "left_modules": 6,
            "right_modules": 6,
            "left_fixture_type": "steel_rack",
            "right_fixture_type": "steel_rack",
            "shelves_per_rack": 6,
            "standard_rack_dimensions": {"width": 100, "depth": 50, "height": 210},
            "chilled_area_m2": 39 if code == "FULYA" else 0,
            "frozen_area_m2": 38 if code == "FULYA" else 0,
            "algida_count": algida_count,
            "martek_plus4_count": integer(row.get("(+)4 Martek")),
            "martek_frozen_count": integer(row.get("-18 Martek")),
            "horizontal_fridge_count": integer(row.get("Banabi Yatay -18")),
            "produce_module_count": integer(row.get("Banabi Yatay meyve Sebze")),
            "produce_chilled_count": 0,
            "new_gen_steel_rack_count": 0,
            "chilled_fixture_count": chilled_total,
            "frozen_fixture_count": frozen_total,
        }

        stores.append({
            "store_code": code,
            "vendor_id": code,
            "store_name": base_name,
            "display_name": name,
            "city": city_from_name(name),
            "region": current_region,
            "store_type": "depot",
            "inventory_source": "DOLAP ENVANTERİ GÜNCEL - TEMMUZ",
            "inventory_note": clean_header(row.get("Açıklama ve Sorunlar", "")),
            "equipment_inventory": inventory,
            "equipment_summary": {
                "chilled_fixture_count": chilled_total,
                "frozen_fixture_count": frozen_total,
                "algida_count": algida_count,
                "martek_plus4_count": integer(row.get("(+)4 Martek")),
                "martek_frozen_count": integer(row.get("-18 Martek")),
            },
            "default_dna": default_dna,
        })

    return sorted(stores, key=lambda item: (item["city"], item["display_name"]))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_store_master.py SOURCE.csv OUTPUT.json")
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    stores = build(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(stores, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(stores)} depots written to {output}")


if __name__ == "__main__":
    main()
