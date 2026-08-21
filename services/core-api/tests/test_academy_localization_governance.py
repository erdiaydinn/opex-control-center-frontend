from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import Principal
from app.modules.academy.localization_schemas import (
    LocaleSettingUpdateRequest,
    TranslationLineageCreateRequest,
    TranslationReviewRequest,
)
from app.modules.academy.localization_service import (
    author_translation_lineage,
    configure_locale,
    decide_translation_review,
    localization_governance_telemetry,
    submit_translation_for_review,
    translation_authority,
)

TENANT = UUID("00000000-0000-0000-0000-00000000a049")
CONTENT = UUID("00000000-0000-0000-0000-00000000c049")
SOURCE_V1 = UUID("00000000-0000-0000-0000-000000001049")
TARGET_FA = UUID("00000000-0000-0000-0000-000000002049")
SOURCE_V2 = UUID("00000000-0000-0000-0000-000000003049")


def _principal(subject: str) -> Principal:
    return Principal(
        subject=subject,
        tenant_id=TENANT,
        roles=("academy_instructor",),
        permissions=("module:academy:view", "action:academy:manageContent"),
        permission_assignments=(),
        auth_mode="development",
    )


async def _tenant_session(subject: str) -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    await session.begin()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(TENANT)},
    )
    await session.execute(
        text("SELECT set_config('app.actor_subject', :subject, true)"),
        {"subject": subject},
    )
    session.info["test_engine"] = engine
    return session


async def _close_session(session: AsyncSession, *, commit: bool) -> None:
    engine = session.info["test_engine"]
    if commit:
        await session.commit()
    else:
        await session.rollback()
    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_localization_governance_maker_checker_and_staleness() -> None:
    settings = get_settings()
    admin_engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            # CI provisions a fresh PostgreSQL database for this acceptance test.
            # Do not delete the tenant during setup/teardown: localization writes
            # durable audit evidence whose tenant FK is intentionally restrictive.
            await connection.execute(
                text("SELECT set_config('app.actor_subject', 'academy-localization-ci', true)")
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO tenants (id, slug, display_name, status)
                    VALUES (
                        :tenant_id,
                        'academy-localization-ci',
                        'Academy Localization CI',
                        'active'
                    )
                    """
                ),
                {"tenant_id": TENANT},
            )
            default_locale = await connection.scalar(
                text(
                    """
                    SELECT locale
                    FROM academy_locale_settings
                    WHERE tenant_id = :tenant_id AND is_default IS TRUE
                    """
                ),
                {"tenant_id": TENANT},
            )
            assert default_locale == "en"

            await connection.execute(
                text(
                    """
                    INSERT INTO academy_content_items (
                        id, tenant_id, content_type, slug, title_i18n, status, created_by
                    ) VALUES (
                        :content_id, :tenant_id, 'sop', 'localization-governance-ci',
                        '{"en":"Safety SOP","fa":"روش ایمنی"}'::jsonb,
                        'published', 'academy-localization-ci'
                    )
                    """
                ),
                {"content_id": CONTENT, "tenant_id": TENANT},
            )
            for version_id, label, number, locale, sha in (
                (SOURCE_V1, "2026.1", 1, "en", "1" * 64),
                (TARGET_FA, "2026.1", 1, "fa", "2" * 64),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO academy_content_versions (
                            id, tenant_id, content_id, version_label, version_number,
                            locale, source_sha256, status, published_at, created_by
                        ) VALUES (
                            :id, :tenant_id, :content_id, :label, :number,
                            :locale, :sha, 'published', CURRENT_TIMESTAMP, 'academy-localization-ci'
                        )
                        """
                    ),
                    {
                        "id": version_id,
                        "tenant_id": TENANT,
                        "content_id": CONTENT,
                        "label": label,
                        "number": number,
                        "locale": locale,
                        "sha": sha,
                    },
                )

        translator = _principal("translator-1")
        session = await _tenant_session(translator.subject)
        try:
            locale_setting = await configure_locale(
                session,
                translator,
                request_id="loc-config-1",
                locale="fa-IR",
                payload=LocaleSettingUpdateRequest(
                    enabled=True,
                    required=True,
                    allow_machine_draft=False,
                ),
            )
            assert locale_setting["locale"] == "fa"
            assert locale_setting["required"] is True

            lineage = await author_translation_lineage(
                session,
                translator,
                request_id="loc-lineage-1",
                payload=TranslationLineageCreateRequest(
                    source_version_id=SOURCE_V1,
                    target_version_id=TARGET_FA,
                    translation_method="human",
                ),
            )
            translation_id = lineage["id"]
            await submit_translation_for_review(
                session,
                translator,
                request_id="loc-submit-1",
                translation_id=translation_id,
            )
            await _close_session(session, commit=True)
        except Exception:
            await _close_session(session, commit=False)
            raise

        same_author_session = await _tenant_session(translator.subject)
        try:
            with pytest.raises(ValueError, match="cannot review own translation"):
                await decide_translation_review(
                    same_author_session,
                    translator,
                    request_id="loc-self-review-1",
                    translation_id=translation_id,
                    payload=TranslationReviewRequest(decision="approved"),
                )
        finally:
            await _close_session(same_author_session, commit=False)

        reviewer = _principal("reviewer-1")
        reviewer_session = await _tenant_session(reviewer.subject)
        try:
            await decide_translation_review(
                reviewer_session,
                reviewer,
                request_id="loc-review-1",
                translation_id=translation_id,
                payload=TranslationReviewRequest(decision="approved"),
            )
            authority = await translation_authority(
                reviewer_session,
                reviewer,
                content_id=CONTENT,
            )
            assert len(authority) == 1
            assert authority[0]["workflow_status"] == "approved"
            assert authority[0]["stale"] is False
            assert authority[0]["authoritative"] is True

            telemetry = await localization_governance_telemetry(reviewer_session, reviewer)
            fa = next(item for item in telemetry["locales"] if item["locale"] == "fa")
            assert telemetry["source_locale"] == "en"
            assert telemetry["source_content_count"] == 1
            assert telemetry["summary"]["required_coverage_percent"] == 100.0
            assert telemetry["summary"]["required_authority_gap_count"] == 0
            assert telemetry["quality_score"] is None
            assert telemetry["quality_score_reason"] == "not_computed_without_linguistic_qa_evidence"
            assert fa["source_content_count"] == 1
            assert fa["lineage_content_count"] == 1
            assert fa["authoritative_content_count"] == 1
            assert fa["missing_lineage_count"] == 0
            assert fa["authority_gap_count"] == 0
            assert fa["coverage_percent"] == 100.0
            await _close_session(reviewer_session, commit=True)
        except Exception:
            await _close_session(reviewer_session, commit=False)
            raise

        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO academy_content_versions (
                        id, tenant_id, content_id, version_label, version_number,
                        locale, source_sha256, status, published_at, created_by
                    ) VALUES (
                        :id, :tenant_id, :content_id, '2026.2', 2,
                        'en', :sha, 'published', CURRENT_TIMESTAMP, 'academy-localization-ci'
                    )
                    """
                ),
                {
                    "id": SOURCE_V2,
                    "tenant_id": TENANT,
                    "content_id": CONTENT,
                    "sha": "3" * 64,
                },
            )

        stale_session = await _tenant_session(reviewer.subject)
        try:
            stale = await translation_authority(
                stale_session,
                reviewer,
                content_id=CONTENT,
            )
            assert stale[0]["latest_published_source_version_id"] == SOURCE_V2
            assert stale[0]["stale"] is True
            assert stale[0]["authoritative"] is False

            stale_telemetry = await localization_governance_telemetry(stale_session, reviewer)
            fa = next(item for item in stale_telemetry["locales"] if item["locale"] == "fa")
            assert stale_telemetry["summary"]["required_coverage_percent"] == 0.0
            assert stale_telemetry["summary"]["required_authority_gap_count"] == 1
            assert stale_telemetry["summary"]["stale_translation_count"] == 1
            assert fa["lineage_content_count"] == 0
            assert fa["authoritative_content_count"] == 0
            assert fa["missing_lineage_count"] == 1
            assert fa["authority_gap_count"] == 1
            assert fa["stale_translation_count"] == 1
            assert fa["coverage_percent"] == 0.0
        finally:
            await _close_session(stale_session, commit=False)
    finally:
        await admin_engine.dispose()
