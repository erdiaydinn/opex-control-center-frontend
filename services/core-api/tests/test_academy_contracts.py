from pathlib import Path
from uuid import UUID

import pytest

from app.core.localization import (
    CONTENT_LOCALE_SET,
    CONTENT_RTL_LOCALES,
    SUPPORTED_LOCALE_SET,
    canonicalize_content_locale,
    canonicalize_locale,
    content_direction,
)
from app.core.security import Principal
from app.modules.academy import skill_gap_service
from app.modules.academy.media import (
    AcademyMediaConfig,
    build_playback_url,
    issue_playback_token,
    verify_playback_token,
)
from app.modules.academy.schemas import (
    ContentCreateRequest,
    DocumentChunkCreate,
    InteractionSetCreateRequest,
    PlaybackHeartbeatRequest,
    QuestionAnswerRequest,
    QuestionCreate,
    QuestionOptionCreate,
    ScenarioCreateRequest,
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


def test_ui_release_locales_stay_narrow_while_academy_content_expands() -> None:
    expected_ui_locales = {
        "tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"
    }
    expected_extended_examples = {"fa", "ru", "ja", "ur", "ckb", "zh-Hans", "pt-PT"}
    assert set(SUPPORTED_LOCALE_SET) == expected_ui_locales
    assert expected_extended_examples.issubset(CONTENT_LOCALE_SET)
    assert canonicalize_locale("fa-IR") is None
    assert canonicalize_content_locale("fa-IR") == "fa"
    assert canonicalize_content_locale("pt_BR") == "pt-BR"
    assert canonicalize_content_locale("zh-CN") == "zh-Hans"


def test_academy_content_locales_normalize_bcp47_aliases() -> None:
    payload = ContentCreateRequest(
        content_type="sop",
        slug="safe-work",
        title_i18n={
            "tr-TR": "Güvenli Çalışma",
            "en-US": "Safe Work",
            "fa-IR": "کار ایمن",
            "ja-JP": "安全な作業",
            "ur-PK": "محفوظ کام",
        },
        version_label="2026.1",
        locale="fa-IR",
    )
    assert payload.locale == "fa"
    assert set(payload.title_i18n) == {"tr", "en", "fa", "ja", "ur"}

    chunk = DocumentChunkCreate(
        chunk_ordinal=1,
        locale="ckb-IQ",
        text_content="ڕێنمایی سەلامەتی",
    )
    assert chunk.locale == "ckb"
    assert QuestionAnswerRequest(question="روش چیست؟", locale="fa-IR").locale == "fa"

    with pytest.raises(ValueError, match="Unsupported locales"):
        ContentCreateRequest(
            content_type="sop",
            slug="unsupported-locale",
            title_i18n={"xx-ZZ": "unsupported"},
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


def test_content_rtl_is_not_arabic_only() -> None:
    expected_rtl_locales = {"ar", "fa", "ur", "ckb", "he", "ps"}
    assert set(CONTENT_RTL_LOCALES) == expected_rtl_locales
    for locale in ("ar", "fa-IR", "ur-PK", "ckb-IQ", "he-IL", "ps-AF"):
        assert content_direction(locale) == "rtl"
    assert content_direction("tr-TR") == "ltr"


def test_verified_playback_heartbeat_contract_rejects_reverse_ranges() -> None:
    with pytest.raises(ValueError, match="to_position_ms"):
        PlaybackHeartbeatRequest(
            sequence_no=1,
            from_position_ms=5000,
            to_position_ms=4000,
            client_elapsed_ms=1000,
        )


def test_interaction_authoring_rejects_duplicate_node_keys() -> None:
    with pytest.raises(ValueError, match="node_key values must be unique"):
        InteractionSetCreateRequest(
            content_version_id=VERSION,
            version_number=1,
            source_fingerprint="a" * 64,
            nodes=[
                {"node_key": "stop", "node_type": "checkpoint", "at_ms": 1000},
                {"node_key": "stop", "node_type": "hotspot", "at_ms": 2000},
            ],
        )


def test_interaction_authoring_matches_multiple_choice_and_cta_authority() -> None:
    payload = InteractionSetCreateRequest(
        content_version_id=VERSION,
        version_number=2,
        source_fingerprint="d" * 64,
        nodes=[
            {
                "node_key": "choose",
                "node_type": "multiple_choice",
                "at_ms": 1000,
                "blocking": True,
                "required": True,
                "score_weight": 1000,
            },
            {
                "node_key": "continue",
                "node_type": "cta",
                "at_ms": 2000,
            },
        ],
    )
    assert [node.node_type for node in payload.nodes] == ["multiple_choice", "cta"]
    assert payload.nodes[0].score_weight == 1000

    with pytest.raises(ValueError):
        InteractionSetCreateRequest(
            content_version_id=VERSION,
            version_number=2,
            source_fingerprint="e" * 64,
            nodes=[
                {"node_key": "legacy", "node_type": "multi_choice", "at_ms": 1000}
            ],
        )


def test_scenario_authoring_requires_valid_closed_graph() -> None:
    scenario = ScenarioCreateRequest(
        content_version_id=VERSION,
        scenario_key="inbound-damaged-case",
        version_number=1,
        title_i18n={"tr-TR": "Hasarlı ürün senaryosu", "en-US": "Damaged item scenario"},
        entry_node_key="start",
        source_fingerprint="b" * 64,
        nodes=[
            {"node_key": "start", "node_type": "decision", "prompt_i18n": {"tr": "Ne yaparsın?"}},
            {
                "node_key": "done",
                "node_type": "outcome",
                "terminal": True,
                "terminal_outcome": "completed",
            },
            {
                "node_key": "retry",
                "node_type": "outcome",
                "terminal": True,
                "terminal_outcome": "remediation",
            },
        ],
        edges=[
            {
                "from_node_key": "start",
                "choice_key": "reject",
                "to_node_key": "done",
                "label_i18n": {"tr": "Hasarlı olarak ayır"},
                "score_delta": 100,
                "correct": True,
            },
            {
                "from_node_key": "start",
                "choice_key": "accept",
                "to_node_key": "retry",
                "label_i18n": {"tr": "Stoğa al"},
                "correct": False,
            },
        ],
        status="published",
    )
    assert scenario.title_i18n["tr"] == "Hasarlı ürün senaryosu"
    assert scenario.title_i18n["en"] == "Damaged item scenario"

    with pytest.raises(ValueError, match="reference declared nodes"):
        ScenarioCreateRequest(
            content_version_id=VERSION,
            scenario_key="invalid-edge",
            version_number=1,
            title_i18n={"en": "Invalid"},
            entry_node_key="start",
            source_fingerprint="c" * 64,
            nodes=[
                {"node_key": "start", "node_type": "decision"},
                {
                    "node_key": "done",
                    "node_type": "outcome",
                    "terminal": True,
                    "terminal_outcome": "completed",
                },
            ],
            edges=[
                {
                    "from_node_key": "start",
                    "choice_key": "bad",
                    "to_node_key": "missing",
                    "label_i18n": {"en": "Bad"},
                }
            ],
        )


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


@pytest.mark.asyncio
async def test_skill_gap_contract_is_self_scoped_and_deterministic(monkeypatch) -> None:
    viewer = principal()
    session_sentinel = object()

    async def fake_context(session, supplied_principal, *, include_learning_context=False):
        assert session is session_sentinel
        assert supplied_principal is viewer
        assert include_learning_context is True
        return {
            "requirements": [
                {
                    "skill_key": "inventory.count",
                    "title_i18n": {"en": "Inventory count"},
                    "description_i18n": {"en": "Count accurately"},
                    "required_level": 4,
                    "role_keys": ["picker"],
                }
            ],
            "proficiencies": [
                {
                    "skill_key": "inventory.count",
                    "observed_level": 2,
                    "evidence_type": "assessment",
                    "evidence_ref": "assessment:academy-contract",
                    "observed_at": "2026-08-21T00:00:00+00:00",
                }
            ],
            "outcomes": [
                {
                    "path_key": "inventory-count-recovery",
                    "title_i18n": {"en": "Inventory count recovery"},
                    "skill_key": "inventory.count",
                    "target_level": 4,
                }
            ],
        }

    monkeypatch.setattr(
        skill_gap_service,
        "list_my_badge_credentials",
        fake_context,
    )
    snapshot = await skill_gap_service.get_my_skill_gap_snapshot(
        session_sentinel,  # type: ignore[arg-type]
        viewer,
    )

    assert snapshot["subject"] == viewer.subject
    assert snapshot["roles"] == ["picker"]
    assert snapshot["gap_count"] == 1
    assert snapshot["gaps"][0]["current_level"] == 2
    assert snapshot["gaps"][0]["required_level"] == 4
    assert snapshot["gaps"][0]["latest_evidence"]["evidence_ref"] == (
        "assessment:academy-contract"
    )
    assert snapshot["recommended_paths"][0]["path_key"] == "inventory-count-recovery"
    assert snapshot["recommendation_policy"] == "deterministic_role_skill_gap_v1"


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


def test_media_secret_is_file_backed_in_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "academy-media.key"
    secret.write_bytes(b"z" * 48)
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_CDN_BASE_URL", "https://cdn.example.test")
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_SIGNING_SECRET_FILE", str(secret))
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_TOKEN_TTL_SECONDS", "90")
    from app.modules.academy.media import load_media_config

    config = load_media_config()
    assert config.token_ttl_seconds == 90
    assert config.signing_secret == b"z" * 48
