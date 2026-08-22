from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import Principal
from app.modules.academy.operational_schemas import (
    OperationalMappingCreateRequest,
    OperationalOutcomeObservationRequest,
    OperationalSignalIngestRequest,
)
from app.modules.academy.operational_service import (
    create_mapping,
    ingest_signal,
    my_readiness,
    record_outcome,
    retire_mapping,
)

TENANT = UUID("00000000-0000-0000-0000-00000000c060")
SKILL = UUID("00000000-0000-0000-0000-000000006060")
PATH = UUID("00000000-0000-0000-0000-000000007060")
EVIDENCE = UUID("00000000-0000-0000-0000-000000008060")
LEARNER = "operational-learner-1"
AUDIT_SERVICE = "audit-readiness-service"
WRONG_SERVICE = "inventory-readiness-service"


def _principal(subject: str) -> Principal:
    return Principal(
        subject=subject,
        tenant_id=TENANT,
        roles=("academy_admin",),
        permissions=("module:academy:view",),
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
async def test_operational_readiness_is_source_bound_self_scoped_and_append_only() -> None:
    settings = get_settings()
    migration_engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with migration_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO tenants (id, slug, display_name, status)
                    VALUES (
                        :tenant_id,
                        'academy-operational-ci',
                        'Academy Operational CI',
                        'active'
                    )
                    """
                ),
                {"tenant_id": TENANT},
            )
            for subject in (LEARNER, AUDIT_SERVICE, WRONG_SERVICE):
                await connection.execute(
                    text(
                        """
                        INSERT INTO memberships (tenant_id, external_subject, status)
                        VALUES (:tenant_id, :subject, 'active')
                        """
                    ),
                    {"tenant_id": TENANT, "subject": subject},
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO academy_skills (
                        id, tenant_id, skill_key, title_i18n, description_i18n,
                        status, created_by
                    ) VALUES (
                        :skill_id, :tenant_id, 'safe-inbound',
                        '{"en":"Safe inbound"}'::jsonb,
                        '{"en":"Operational inbound readiness"}'::jsonb,
                        'active', 'academy-operational-ci'
                    )
                    """
                ),
                {"skill_id": SKILL, "tenant_id": TENANT},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO academy_learning_paths (
                        id, tenant_id, key, title_i18n, description_i18n,
                        certificate_enabled, completion_policy, status, created_by
                    ) VALUES (
                        :path_id, :tenant_id, 'safe-inbound-remediation',
                        '{"en":"Safe inbound remediation"}'::jsonb,
                        '{}'::jsonb, true, '{}'::jsonb, 'published',
                        'academy-operational-ci'
                    )
                    """
                ),
                {"path_id": PATH, "tenant_id": TENANT},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO academy_skill_evidence (
                        id, tenant_id, subject, skill_id, observed_level,
                        evidence_type, evidence_ref, recorded_by, observed_at
                    ) VALUES (
                        :id, :tenant_id, :subject, :skill_id, 1,
                        'manager_verified', 'audit:baseline',
                        'academy-operational-ci', :observed_at
                    )
                    """
                ),
                {
                    "id": EVIDENCE,
                    "tenant_id": TENANT,
                    "subject": LEARNER,
                    "skill_id": SKILL,
                    "observed_at": now - timedelta(days=5),
                },
            )

        admin = _principal("academy-operational-admin")
        admin_session = await _tenant_session(admin)
        try:
            mapping = await create_mapping(
                admin_session,
                admin,
                OperationalMappingCreateRequest(
                    source_subject=AUDIT_SERVICE,
                    source_domain="audit",
                    signal_type="safety_deviation",
                    skill_id=SKILL,
                    required_level=3,
                    recommended_path_id=PATH,
                    minimum_severity=2,
                    metric_key="audit.safety_deviation_rate",
                    metric_direction="lower_better",
                    mapping_version=1,
                ),
            )
            mapping_id = mapping["id"]
            await _close_session(admin_session, commit=True)
        except Exception:
            await _close_session(admin_session, commit=False)
            raise

        wrong = _principal(WRONG_SERVICE)
        wrong_session = await _tenant_session(wrong)
        try:
            with pytest.raises(ValueError, match="authorized"):
                await ingest_signal(
                    wrong_session,
                    wrong,
                    OperationalSignalIngestRequest(
                        source_domain="audit",
                        signal_type="safety_deviation",
                        subject=LEARNER,
                        severity=4,
                        source_ref="audit-run-1:item-9",
                        source_version="1",
                        source_fingerprint="a" * 64,
                        occurred_at=now,
                    ),
                    request_id="wrong-source-1",
                )
        finally:
            await _close_session(wrong_session, commit=False)

        source = _principal(AUDIT_SERVICE)
        source_session = await _tenant_session(source)
        try:
            created = await ingest_signal(
                source_session,
                source,
                OperationalSignalIngestRequest(
                    source_domain="audit",
                    signal_type="safety_deviation",
                    subject=LEARNER,
                    severity=4,
                    source_ref="audit-run-1:item-9",
                    source_version="1",
                    source_fingerprint="b" * 64,
                    occurred_at=now,
                ),
                request_id="signal-1",
            )
            assert created["event"]["source_subject"] == AUDIT_SERVICE
            assert len(created["remediations"]) == 1
            remediation = created["remediations"][0]
            assert remediation["skill_id"] == SKILL
            assert remediation["current_level"] == 1
            assert remediation["required_level"] == 3
            assert remediation["recommended_path_id"] == PATH
            remediation_id = remediation["id"]
            await _close_session(source_session, commit=True)
        except Exception:
            await _close_session(source_session, commit=False)
            raise

        duplicate_session = await _tenant_session(source)
        try:
            with pytest.raises(ValueError, match="already ingested"):
                await ingest_signal(
                    duplicate_session,
                    source,
                    OperationalSignalIngestRequest(
                        source_domain="audit",
                        signal_type="safety_deviation",
                        subject=LEARNER,
                        severity=4,
                        source_ref="audit-run-1:item-9",
                        source_version="1",
                        source_fingerprint="b" * 64,
                        occurred_at=now,
                    ),
                    request_id="signal-replay",
                )
        finally:
            await _close_session(duplicate_session, commit=False)

        learner = _principal(LEARNER)
        learner_session = await _tenant_session(learner)
        try:
            readiness = await my_readiness(learner_session, learner)
            assert len(readiness) == 1
            assert readiness[0]["remediation_id"] == remediation_id
            assert readiness[0]["gap"] == 2
            assert readiness[0]["causal_attribution"] is False
            await _close_session(learner_session, commit=False)
        except Exception:
            await _close_session(learner_session, commit=False)
            raise

        other = _principal("other-learner")
        other_session = await _tenant_session(other)
        try:
            assert await my_readiness(other_session, other) == []
        finally:
            await _close_session(other_session, commit=False)

        wrong_observation_session = await _tenant_session(wrong)
        try:
            with pytest.raises(ValueError, match="not authoritative"):
                await record_outcome(
                    wrong_observation_session,
                    wrong,
                    remediation_id=remediation_id,
                    payload=OperationalOutcomeObservationRequest(
                        source_domain="audit",
                        source_ref="audit-window-1",
                        source_version="1",
                        source_fingerprint="c" * 64,
                        baseline_value=0.20,
                        observed_value=0.10,
                        window_start=now + timedelta(days=1),
                        window_end=now + timedelta(days=8),
                        observed_at=now + timedelta(days=8),
                    ),
                    request_id="wrong-observation",
                )
        finally:
            await _close_session(wrong_observation_session, commit=False)

        observation_session = await _tenant_session(source)
        try:
            observation = await record_outcome(
                observation_session,
                source,
                remediation_id=remediation_id,
                payload=OperationalOutcomeObservationRequest(
                    source_domain="audit",
                    source_ref="audit-window-1",
                    source_version="1",
                    source_fingerprint="d" * 64,
                    baseline_value=0.20,
                    observed_value=0.10,
                    window_start=now + timedelta(days=1),
                    window_end=now + timedelta(days=8),
                    observed_at=now + timedelta(days=8),
                ),
                request_id="observation-1",
            )
            assert float(observation["observed_delta"]) == pytest.approx(-0.10)
            assert observation["causal_attribution"] is False
            await _close_session(observation_session, commit=True)
        except Exception:
            await _close_session(observation_session, commit=False)
            raise

        mutation_session = await _tenant_session(source)
        try:
            with pytest.raises(DBAPIError):
                await mutation_session.execute(
                    text(
                        """
                        UPDATE academy_operational_remediations
                        SET required_level=4
                        WHERE tenant_id=:tenant_id AND id=:remediation_id
                        """
                    ),
                    {"tenant_id": TENANT, "remediation_id": remediation_id},
                )
        finally:
            await _close_session(mutation_session, commit=False)

        retire_session = await _tenant_session(admin)
        try:
            retired = await retire_mapping(
                retire_session,
                admin,
                mapping_id=mapping_id,
                reason="Mapping superseded after policy review",
                request_id="retire-1",
            )
            assert retired["mapping_id"] == mapping_id
            await _close_session(retire_session, commit=True)
        except Exception:
            await _close_session(retire_session, commit=False)
            raise

        retired_signal_session = await _tenant_session(source)
        try:
            with pytest.raises(ValueError, match="authorized"):
                await ingest_signal(
                    retired_signal_session,
                    source,
                    OperationalSignalIngestRequest(
                        source_domain="audit",
                        signal_type="safety_deviation",
                        subject=LEARNER,
                        severity=4,
                        source_ref="audit-run-2:item-4",
                        source_version="1",
                        source_fingerprint="e" * 64,
                        occurred_at=now + timedelta(days=9),
                    ),
                    request_id="retired-mapping-signal",
                )
        finally:
            await _close_session(retired_signal_session, commit=False)
    finally:
        await migration_engine.dispose()
