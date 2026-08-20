from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import Principal
from app.modules.academy.credentials_schemas import (
    BadgeAwardIssueRequest,
    BadgeDefinitionCreateRequest,
    BadgeRetirementRequest,
    BadgeRevocationRequest,
)
from app.modules.academy.credentials_service import (
    create_definition,
    issue_award,
    my_credential,
    my_credentials,
    retire_definition,
    revoke_award,
)

TENANT = UUID("00000000-0000-0000-0000-00000000c050")
OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000c051")
SKILL = UUID("00000000-0000-0000-0000-000000005050")
LOW_EVIDENCE = UUID("00000000-0000-0000-0000-000000001050")
HIGH_EVIDENCE = UUID("00000000-0000-0000-0000-000000002050")
SECOND_HIGH_EVIDENCE = UUID("00000000-0000-0000-0000-000000003050")
LEARNER = "credential-learner-1"


def _principal(subject: str, *, tenant_id: UUID = TENANT) -> Principal:
    return Principal(
        subject=subject,
        tenant_id=tenant_id,
        roles=("academy_admin",),
        permissions=(
            "module:academy:view",
            "action:academy:manageContent",
            "action:academy:revokeCompletion",
        ),
        permission_assignments=(),
        auth_mode="development",
    )


async def _tenant_session(principal: Principal) -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    await session.begin()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(principal.tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('app.actor_subject', :subject, true)"),
        {"subject": principal.subject},
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
async def test_credentials_are_evidence_bound_self_scoped_and_append_only() -> None:
    settings = get_settings()
    admin_engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO tenants (id, slug, display_name, status)
                    VALUES (:tenant_id, 'academy-credential-ci', 'Academy Credential CI', 'active')
                    """
                ),
                {"tenant_id": TENANT},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO academy_skills (
                        id, tenant_id, skill_key, title_i18n, description_i18n,
                        status, created_by
                    ) VALUES (
                        :skill_id, :tenant_id, 'safe-picking',
                        '{"en":"Safe picking"}'::jsonb,
                        '{"en":"Verified safe picking proficiency"}'::jsonb,
                        'active', 'academy-credential-ci'
                    )
                    """
                ),
                {"skill_id": SKILL, "tenant_id": TENANT},
            )
            for evidence_id, level, evidence_ref in (
                (LOW_EVIDENCE, 2, "assessment:low"),
                (HIGH_EVIDENCE, 4, "assessment:high"),
                (SECOND_HIGH_EVIDENCE, 5, "assessment:second-high"),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO academy_skill_evidence (
                            id, tenant_id, subject, skill_id, observed_level,
                            evidence_type, evidence_ref, recorded_by
                        ) VALUES (
                            :id, :tenant_id, :subject, :skill_id, :level,
                            'assessment', :evidence_ref, 'academy-credential-ci'
                        )
                        """
                    ),
                    {
                        "id": evidence_id,
                        "tenant_id": TENANT,
                        "subject": LEARNER,
                        "skill_id": SKILL,
                        "level": level,
                        "evidence_ref": evidence_ref,
                    },
                )

        issuer = _principal("credential-issuer-1")
        session = await _tenant_session(issuer)
        try:
            definition = await create_definition(
                session,
                issuer,
                request_id="credential-definition-1",
                payload=BadgeDefinitionCreateRequest(
                    badge_key="safe-picking.level-3",
                    version_number=1,
                    skill_id=SKILL,
                    minimum_level=3,
                    title_i18n={"en": "Safe Picking Level 3"},
                    description_i18n={"en": "Evidence-bound Academy credential"},
                    criteria_i18n={"en": "Requires verified level 3 or higher"},
                    validity_days=365,
                ),
            )
            definition_id = definition["id"]
            await _close_session(session, commit=True)
        except Exception:
            await _close_session(session, commit=False)
            raise

        low_session = await _tenant_session(issuer)
        try:
            with pytest.raises(ValueError, match="not eligible"):
                await issue_award(
                    low_session,
                    issuer,
                    request_id="credential-low-issue-1",
                    payload=BadgeAwardIssueRequest(
                        badge_definition_id=definition_id,
                        skill_evidence_id=LOW_EVIDENCE,
                    ),
                )
        finally:
            await _close_session(low_session, commit=False)

        issue_session = await _tenant_session(issuer)
        try:
            award = await issue_award(
                issue_session,
                issuer,
                request_id="credential-issue-1",
                payload=BadgeAwardIssueRequest(
                    badge_definition_id=definition_id,
                    skill_evidence_id=HIGH_EVIDENCE,
                ),
            )
            assert award["subject"] == LEARNER
            assert award["skill_id"] == SKILL
            assert award["observed_level"] == 4
            assert award["evidence_type"] == "assessment"
            assert award["evidence_ref"] == "assessment:high"
            assert award["expires_at"] is not None
            award_id = award["id"]
            await _close_session(issue_session, commit=True)
        except Exception:
            await _close_session(issue_session, commit=False)
            raise

        duplicate_session = await _tenant_session(issuer)
        try:
            with pytest.raises(ValueError, match="already exists"):
                await issue_award(
                    duplicate_session,
                    issuer,
                    request_id="credential-issue-duplicate",
                    payload=BadgeAwardIssueRequest(
                        badge_definition_id=definition_id,
                        skill_evidence_id=HIGH_EVIDENCE,
                    ),
                )
        finally:
            await _close_session(duplicate_session, commit=False)

        learner = _principal(LEARNER)
        learner_session = await _tenant_session(learner)
        try:
            items = await my_credentials(learner_session, learner)
            assert len(items) == 1
            assert items[0]["badge_award_id"] == award_id
            assert items[0]["valid"] is True
            assert items[0]["revoked"] is False
            assert items[0]["expired"] is False
            assert items[0]["credential_profile"] == "eay.academy.badge.v1"
            assert items[0]["signed_portable_credential"] is False
            assert await my_credential(
                learner_session,
                learner,
                badge_award_id=award_id,
            ) is not None
        finally:
            await _close_session(learner_session, commit=False)

        other_subject = _principal("credential-other-subject")
        other_subject_session = await _tenant_session(other_subject)
        try:
            assert await my_credentials(other_subject_session, other_subject) == []
            assert await my_credential(
                other_subject_session,
                other_subject,
                badge_award_id=award_id,
            ) is None
        finally:
            await _close_session(other_subject_session, commit=False)

        other_tenant = _principal(LEARNER, tenant_id=OTHER_TENANT)
        other_tenant_session = await _tenant_session(other_tenant)
        try:
            assert await my_credentials(other_tenant_session, other_tenant) == []
        finally:
            await _close_session(other_tenant_session, commit=False)

        retire_session = await _tenant_session(issuer)
        try:
            await retire_definition(
                retire_session,
                issuer,
                request_id="credential-retire-1",
                badge_definition_id=definition_id,
                payload=BadgeRetirementRequest(reason="Superseded by a new governed badge version"),
            )
            await _close_session(retire_session, commit=True)
        except Exception:
            await _close_session(retire_session, commit=False)
            raise

        retired_issue_session = await _tenant_session(issuer)
        try:
            with pytest.raises(ValueError, match="not eligible"):
                await issue_award(
                    retired_issue_session,
                    issuer,
                    request_id="credential-retired-issue-1",
                    payload=BadgeAwardIssueRequest(
                        badge_definition_id=definition_id,
                        skill_evidence_id=SECOND_HIGH_EVIDENCE,
                    ),
                )
        finally:
            await _close_session(retired_issue_session, commit=False)

        revoke_session = await _tenant_session(issuer)
        try:
            await revoke_award(
                revoke_session,
                issuer,
                request_id="credential-revoke-1",
                badge_award_id=award_id,
                payload=BadgeRevocationRequest(
                    reason="Credential withdrawn after governance review"
                ),
            )
            await _close_session(revoke_session, commit=True)
        except Exception:
            await _close_session(revoke_session, commit=False)
            raise

        revoked_learner_session = await _tenant_session(learner)
        try:
            revoked = await my_credential(
                revoked_learner_session,
                learner,
                badge_award_id=award_id,
            )
            assert revoked is not None
            assert revoked["revoked"] is True
            assert revoked["valid"] is False
            assert revoked["revoked_at"] is not None
        finally:
            await _close_session(revoked_learner_session, commit=False)

        mutation_session = await _tenant_session(issuer)
        try:
            with pytest.raises(DBAPIError):
                await mutation_session.execute(
                    text(
                        """
                        UPDATE academy_badge_awards
                        SET issuer_subject = 'tampered'
                        WHERE tenant_id = :tenant_id AND id = :award_id
                        """
                    ),
                    {"tenant_id": TENANT, "award_id": award_id},
                )
        finally:
            await _close_session(mutation_session, commit=False)
    finally:
        # This acceptance deliberately leaves its tenant/evidence in the ephemeral
        # CI database because credential operations emit platform WORM audit rows.
        await admin_engine.dispose()
