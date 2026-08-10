from datetime import date
from pathlib import Path

import pytest

from app.legal_engine import (
    LegalEngine,
    LegalInstrumentUpsert,
    LegalRequirementUpsert,
)


def _engine(tmp_path: Path) -> LegalEngine:
    return LegalEngine(tmp_path / "legal.db")


def _verified_instrument(engine: LegalEngine) -> None:
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="law-1",
            title="Test Food Regulation",
            instrument_type="regulation",
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 1),
            official_gazette_number="33000",
            source_url="https://www.resmigazete.gov.tr/eskiler/2026/01/test.htm",
            verification_status="verified",
            topics=["food"],
        )
    )


def test_verified_instrument_requires_binding_source():
    with pytest.raises(ValueError):
        LegalInstrumentUpsert(
            id="law-1",
            title="Untrusted Legal Claim",
            instrument_type="regulation",
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 1),
            source_url="https://example.com/law",
            verification_status="verified",
        )


def test_legal_requirement_requires_verified_instrument(tmp_path: Path):
    engine = _engine(tmp_path)
    with pytest.raises(ValueError):
        engine.upsert_requirement(
            LegalRequirementUpsert(
                id="legal-temp",
                authority="legal",
                source_id="missing-law",
                scope="chilled-storage",
                dimension="max_temperature_c",
                operator="<=",
                numeric_value=8,
                unit="C",
            )
        )


def test_company_stricter_than_maximum_is_safe(tmp_path: Path):
    engine = _engine(tmp_path)
    _verified_instrument(engine)
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="legal-temp",
            authority="legal",
            source_id="law-1",
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=8,
            unit="C",
            effective_from=date(2026, 1, 1),
        )
    )
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="company-temp",
            authority="company",
            source_id="sop-1",
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=5,
            unit="C",
            effective_from=date(2026, 1, 1),
        )
    )

    findings = engine.compare_company_to_law(date(2026, 8, 10))
    assert len(findings) == 1
    assert findings[0].status == "company_stricter"
    assert findings[0].requires_human_review is False


def test_company_weaker_than_legal_maximum_is_conflict(tmp_path: Path):
    engine = _engine(tmp_path)
    _verified_instrument(engine)
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="legal-temp",
            authority="legal",
            source_id="law-1",
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=8,
            unit="C",
        )
    )
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="company-temp",
            authority="company",
            source_id="sop-1",
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=10,
            unit="C",
        )
    )

    finding = engine.compare_company_to_law(date(2026, 8, 10))[0]
    assert finding.status == "company_weaker_conflict"
    assert finding.requires_human_review is True


def test_historical_effective_date_is_respected(tmp_path: Path):
    engine = _engine(tmp_path)
    _verified_instrument(engine)
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="legal-old",
            authority="legal",
            source_id="law-1",
            scope="label",
            dimension="minimum_font_mm",
            operator=">=",
            numeric_value=1.0,
            unit="mm",
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 6, 30),
        )
    )
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="company-current",
            authority="company",
            source_id="sop-1",
            scope="label",
            dimension="minimum_font_mm",
            operator=">=",
            numeric_value=1.1,
            unit="mm",
            effective_from=date(2026, 1, 1),
        )
    )
    assert engine.compare_company_to_law(date(2026, 5, 1))[0].status == "company_stricter"
    assert engine.compare_company_to_law(date(2026, 8, 10))[0].status == "missing_legal_baseline"
