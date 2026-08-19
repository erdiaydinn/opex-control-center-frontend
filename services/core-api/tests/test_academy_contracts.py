import os
from pathlib import Path
from uuid import UUID

import pytest

from app.core.security import Principal
from app.modules.academy.localization import (
    CORE_RELEASE_LOCALES,
    direction_for_locale,
    localization_contract,
    metadata_fallback_chain,
)
from app.modules.academy.media import (
    AcademyMediaConfig,
    build_playback_url,
    issue_playback_token,
    verify_playback_token,
)
from app.modules.academy.schemas import (
    ContentCreateRequest,
    DocumentChunkCreate,
    QuestionAnswerRequest,
    QuestionCreate,
    QuestionOptionCreate,
)

TENANT = UUID("00000000-0000-0000-0000-00000000a001")
MEDIA = UUID("00000000-0000-0000-0000-00000000b001")
VERSION = UUID("00000000-0000-0000-0000-00000000c001")


def principal() -> Principal:
    return Principal(
        subject="employee-1",
        tenant_id=TENANT,
        roles=("picker",),
        permissions=(),
        permission_assignments=(),
        auth_mode="development",
    )


def test_locales_support_core_release_and_extended_content_tiers() -> None:
    payload = ContentCreateRequest(
        content_type="sop",
        slug="safe-work",
        title_i18n={
            "tr-TR": "Güvenli Çalışma",
            "fr-FR": "Travail sûr",
            "fa-IR": "کار ایمن",
        },
        version_label="2026.1",
        locale="tr-TR",
    )
    assert payload.locale == "tr"
    assert payload.title_i18n["tr"] == "Güvenli Çalışma"
    assert payload.title_i18n["fr"] == "Travail sûr"
    assert payload.title_i18n["fa"] == "کار ایمن"

    chunk = DocumentChunkCreate(
        chunk_ordinal=1,
        locale="ur-PK",
        text_content="محفوظ کام",
    )
    assert chunk.locale == "ur"

    question = QuestionAnswerRequest(question="Prosedür nedir?", locale="pt_BR")
    assert question.locale == "pt-BR"

    with pytest.raises(ValueError, match="Unsupported locale"):
        ContentCreateRequest(
            content_type="sop",
            slug="bad-locale",
            title_i18n={"xx-ZZ": "Unsupported"},
            version_label="1",
        )


def test_duplicate_locale_aliases_fail_closed() -> None:
    with pytest.raises(ValueError, match="Duplicate locale after normalization"):
        ContentCreateRequest(
            content_type="sop",
            slug="duplicate-locale",
            title_i18n={"tr": "A", "tr-TR": "B"},
            version_label="1",
        )


def test_localization_contract_separates_ui_release_from_content_support() -> None:
    contract = localization_contract()
    assert tuple(contract["core_release_locales"]) == CORE_RELEASE_LOCALES
    assert "fr" in contract["core_release_locales"]
    assert "pt-BR" in contract["core_release_locales"]
    assert "fa" in contract["extended_content_locales"]
    assert "ru" in contract["extended_content_locales"]
    assert contract["learning_evidence_fallback_policy"] == "exact-locale-only"


def test_rtl_contract_covers_arabic_script_languages() -> None:
    assert direction_for_locale("ar") == "rtl"
    assert direction_for_locale("fa-IR") == "rtl"
    assert direction_for_locale("ur-PK") == "rtl"
    assert direction_for_locale("ckb-IQ") == "rtl"
    assert direction_for_locale("he-IL") == "rtl"
    assert direction_for_locale("tr-TR") == "ltr"
    assert metadata_fallback_chain("fa-IR") == ("fa", "en", "tr")


def test_single_choice_requires_exactly_one_correct_option() -> None:
    with pytest.raises(ValueError, match="exactly one correct"):
        QuestionCreate(
            question_type="single_choice",
            prompt_i18n={"en": "Choose"},
            options=[
                QuestionOptionCreate(label_i18n={"en": "A"}, is_correct=True),
                QuestionOptionCreate(label_i18n={"en": "B"}, is_correct=True),
            ],
        )


def test_playback_token_is_short_lived_and_scope_bound() -> None:
    config = AcademyMediaConfig(
        cdn_base_url="https://academy-cdn.example.test",
        signing_secret=b"x" * 32,
        token_ttl_seconds=120,
    )
    token, expires_at = issue_playback_token(
        config,
        principal(),
        media_id=MEDIA,
        content_version_id=VERSION,
        delivery_key="tenant-a/video-1",
        now=1000,
    )
    assert expires_at == 1120
    payload = verify_playback_token(
        config,
        token,
        tenant_id=TENANT,
        subject="employee-1",
        media_id=MEDIA,
        content_version_id=VERSION,
        delivery_key="tenant-a/video-1",
        now=1050,
    )
    assert payload["tenant_id"] == str(TENANT)
    with pytest.raises(ValueError, match="scope mismatch"):
        verify_playback_token(
            config,
            token,
            tenant_id=TENANT,
            subject="employee-2",
            media_id=MEDIA,
            content_version_id=VERSION,
            delivery_key="tenant-a/video-1",
            now=1050,
        )
    with pytest.raises(ValueError, match="expired"):
        verify_playback_token(
            config,
            token,
            tenant_id=TENANT,
            subject="employee-1",
            media_id=MEDIA,
            content_version_id=VERSION,
            delivery_key="tenant-a/video-1",
            now=1120,
        )


def test_playback_url_never_contains_object_storage_coordinates() -> None:
    config = AcademyMediaConfig(
        cdn_base_url="https://academy-cdn.example.test",
        signing_secret=b"x" * 32,
        token_ttl_seconds=120,
    )
    url = build_playback_url(
        config,
        delivery_key="tenant-a/video-1",
        manifest_path="hls/master.m3u8",
        token="abc.def",
        delivery_mode="hls",
    )
    assert url.startswith("https://academy-cdn.example.test/")
    assert "s3://" not in url
    assert "bucket" not in url
    assert "eay_token=" in url


def test_media_secret_is_file_backed_in_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "academy-media.key"
    secret.write_bytes(b"z" * 48)
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_CDN_BASE_URL", "https://cdn.example.test")
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_SIGNING_SECRET_FILE", str(secret))
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_TOKEN_TTL_SECONDS", "90")
    from app.modules.academy.media import load_media_config

    config = load_media_config()
    assert config.token_ttl_seconds == 90
    assert config.signing_secret == b"z" * 48
