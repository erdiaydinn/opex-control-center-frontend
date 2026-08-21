"""Governed recruitment orchestration for pipeline, interviews, offers and onboarding.

This is deliberately independent from any country-specific government portal.
It gives EAY a globally reusable Hiring lifecycle and keeps external legal/e-sign
providers behind explicit future adapters rather than treating an internal click
as a qualified/legal electronic signature.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import secrets
from typing import Any
from uuid import UUID, uuid4

from app.modules.workforce import persistence


class RecruitmentOrchestrationError(ValueError):
    pass


REQUIRED_SCHEMA_VERSION = 44
_TERMINAL_OFFER_EVENTS = {"ACCEPTED", "DECLINED", "WITHDRAWN", "EXPIRED"}
_DEFAULT_ONBOARDING_TASKS = (
    {
        "task_key": "HR_EMPLOYMENT_PACKET",
        "title": "Employment packet and policy acknowledgement",
        "owner_role": "HR",
        "required": True,
        "due_hours": 24,
        "dependencies": [],
    },
    {
        "task_key": "IT_IDENTITY_ACCOUNT",
        "title": "Corporate identity and account provisioning",
        "owner_role": "IT",
        "required": True,
        "due_hours": 48,
        "dependencies": ["HR_EMPLOYMENT_PACKET"],
    },
    {
        "task_key": "ADMIN_ASSET_UNIFORM",
        "title": "Asset, device and uniform preparation",
        "owner_role": "ADMIN",
        "required": True,
        "due_hours": 48,
        "dependencies": ["HR_EMPLOYMENT_PACKET"],
    },
    {
        "task_key": "ACADEMY_MANDATORY_LEARNING",
        "title": "Mandatory Academy learning assigned",
        "owner_role": "ACADEMY",
        "required": True,
        "due_hours": 72,
        "dependencies": ["HR_EMPLOYMENT_PACKET"],
    },
    {
        "task_key": "OPS_FIRST_SHIFT_READY",
        "title": "Manager, roster and first-shift readiness",
        "owner_role": "OPERATIONS",
        "required": True,
        "due_hours": 72,
        "dependencies": ["IT_IDENTITY_ACCOUNT", "ADMIN_ASSET_UNIFORM"],
    },
)


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_ready() -> None:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise RecruitmentOrchestrationError(
            f"Recruitment orchestration PostgreSQL V{REQUIRED_SCHEMA_VERSION} olmadan kullanılamaz."
        )


def _candidate(request_id: str, candidate_id: str) -> tuple[dict, dict]:
    from .service import list_requests

    record = next((item for item in list_requests() if item.get("id") == request_id), None)
    candidate = next(
        (item for item in (record or {}).get("candidates", []) if item.get("id") == candidate_id),
        None,
    )
    if record is None or candidate is None:
        raise RecruitmentOrchestrationError("Recruitment request/candidate bulunamadı.")
    return record, candidate


def _stage_rows(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 2 <= len(stages) <= 20:
        raise RecruitmentOrchestrationError("Pipeline 2-20 stage içermelidir.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(stages):
        key = str(raw.get("key") or "").strip().upper()
        label = str(raw.get("label") or key).strip()
        if not key or len(key) > 64 or key in seen:
            raise RecruitmentOrchestrationError("Pipeline stage anahtarları benzersiz ve geçerli olmalıdır.")
        if not label or len(label) > 160:
            raise RecruitmentOrchestrationError("Pipeline stage etiketi geçersiz.")
        seen.add(key)
        sla_hours = int(raw.get("sla_hours", 72))
        if sla_hours < 1 or sla_hours > 24 * 60:
            raise RecruitmentOrchestrationError("Stage SLA 1 saat ile 60 gün arasında olmalıdır.")
        min_scorecards = int(raw.get("min_scorecards", 0))
        if min_scorecards < 0 or min_scorecards > 20:
            raise RecruitmentOrchestrationError("Stage scorecard gereksinimi geçersiz.")
        min_average_score = raw.get("min_average_score")
        if min_average_score is not None:
            min_average_score = float(min_average_score)
            if min_average_score < 0 or min_average_score > 100:
                raise RecruitmentOrchestrationError("Minimum interview skoru 0-100 arasında olmalıdır.")
        normalized.append(
            {
                "key": key,
                "label": label,
                "order": index,
                "sla_hours": sla_hours,
                "min_scorecards": min_scorecards,
                "min_average_score": min_average_score,
                "allow_skip": bool(raw.get("allow_skip", False)),
            }
        )
    if normalized[-1]["key"] != "READY_TO_HIRE":
        raise RecruitmentOrchestrationError("Pipeline son stage READY_TO_HIRE olmalıdır.")
    return normalized


def create_pipeline_template(
    *, template_key: str, name: str, stages: list[dict[str, Any]], actor: str
) -> dict:
    _ensure_ready()
    normalized_key = str(template_key).strip().upper()
    if not normalized_key or len(normalized_key) > 80:
        raise RecruitmentOrchestrationError("Pipeline template_key geçersiz.")
    if not str(name).strip() or len(str(name).strip()) > 180:
        raise RecruitmentOrchestrationError("Pipeline adı geçersiz.")
    normalized_stages = _stage_rows(stages)
    tenant = persistence.tenant_id()
    template_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT COALESCE(max(version),0)+1 FROM recruitment.pipeline_templates WHERE tenant_id=%s AND template_key=%s",
            (tenant, normalized_key),
        )
        version = int(cursor.fetchone()[0])
        cursor.execute(
            """INSERT INTO recruitment.pipeline_templates(
                 tenant_id,template_id,template_key,version,name,stages,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (
                tenant,
                template_id,
                normalized_key,
                version,
                str(name).strip(),
                json.dumps(normalized_stages, ensure_ascii=False),
                actor,
            ),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_PIPELINE_TEMPLATE_CREATED",
            actor,
            {"template_id": str(template_id), "template_key": normalized_key, "version": version},
        )
        database.commit()
    return {
        "template_id": str(template_id),
        "template_key": normalized_key,
        "version": version,
        "name": str(name).strip(),
        "stages": normalized_stages,
        "immutable": True,
    }


def list_pipeline_templates() -> list[dict]:
    _ensure_ready()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT template_id,template_key,version,name,stages,created_at,created_by
               FROM recruitment.pipeline_templates
               WHERE tenant_id=%s ORDER BY template_key,version DESC""",
            (persistence.tenant_id(),),
        )
        return [
            {
                "template_id": str(row[0]),
                "template_key": row[1],
                "version": int(row[2]),
                "name": row[3],
                "stages": row[4],
                "created_at": row[5].isoformat(),
                "created_by": row[6],
            }
            for row in cursor.fetchall()
        ]


def assign_pipeline(request_id: str, candidate_id: str, template_id: str, actor: str) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    try:
        template_uuid = UUID(str(template_id))
    except ValueError as error:
        raise RecruitmentOrchestrationError("Pipeline template kimliği geçersiz.") from error
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT stages FROM recruitment.pipeline_templates WHERE tenant_id=%s AND template_id=%s",
            (tenant, template_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentOrchestrationError("Pipeline template bulunamadı.")
        stages = list(row[0])
        first_stage = stages[0]["key"]
        cursor.execute(
            """INSERT INTO recruitment.pipeline_assignments(
                 tenant_id,request_id,candidate_id,template_id,current_stage,stage_entered_at,assigned_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (tenant_id,request_id,candidate_id) DO NOTHING
               RETURNING revision""",
            (tenant, request_id, candidate_id, template_uuid, first_stage, now, actor),
        )
        if cursor.fetchone() is None:
            raise RecruitmentOrchestrationError("Aday pipeline ataması zaten mevcut ve yerinde değiştirilemez.")
        event_id = uuid4()
        cursor.execute(
            """INSERT INTO recruitment.pipeline_stage_events(
                 tenant_id,event_id,request_id,candidate_id,template_id,from_stage,to_stage,reason,actor,occurred_at
               ) VALUES(%s,%s,%s,%s,%s,NULL,%s,'PIPELINE_ASSIGNED',%s,%s)""",
            (tenant, event_id, request_id, candidate_id, template_uuid, first_stage, actor, now),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_PIPELINE_ASSIGNED",
            actor,
            {"record_id": request_id, "candidate_id": candidate_id, "template_id": str(template_uuid), "stage": first_stage},
        )
        database.commit()
    return candidate_orchestration_summary(request_id, candidate_id)


def _assignment_locked(cursor, tenant: str, request_id: str, candidate_id: str):
    cursor.execute(
        """SELECT a.template_id,a.current_stage,a.stage_entered_at,a.revision,t.stages
           FROM recruitment.pipeline_assignments a
           JOIN recruitment.pipeline_templates t
             ON t.tenant_id=a.tenant_id AND t.template_id=a.template_id
           WHERE a.tenant_id=%s AND a.request_id=%s AND a.candidate_id=%s
           FOR UPDATE OF a""",
        (tenant, request_id, candidate_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise RecruitmentOrchestrationError("Aday için pipeline ataması bulunamadı.")
    return row


def _scorecard_gate(cursor, tenant: str, request_id: str, candidate_id: str, stage: dict) -> None:
    minimum = int(stage.get("min_scorecards") or 0)
    if minimum <= 0:
        return
    cursor.execute(
        """SELECT count(*),COALESCE(avg(overall_score),0),bool_or(conflict_declared)
           FROM recruitment.interview_scorecards
           WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s AND stage=%s""",
        (tenant, request_id, candidate_id, stage["key"]),
    )
    count, average, any_conflict = cursor.fetchone()
    if int(count) < minimum:
        raise RecruitmentOrchestrationError(
            f"{stage['key']} stage için en az {minimum} bağımsız scorecard gerekir."
        )
    if any_conflict:
        raise RecruitmentOrchestrationError("Conflict-of-interest işaretli scorecard varken stage ilerletilemez.")
    threshold = stage.get("min_average_score")
    if threshold is not None and float(average) < float(threshold):
        raise RecruitmentOrchestrationError(
            f"Interview ortalaması {float(average):.1f}; gerekli eşik {float(threshold):.1f}."
        )


def transition_stage(
    request_id: str, candidate_id: str, to_stage: str, reason: str, actor: str
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    tenant = persistence.tenant_id()
    target = str(to_stage).strip().upper()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        template_id, current, entered_at, revision, stages = _assignment_locked(
            cursor, tenant, request_id, candidate_id
        )
        stage_rows = list(stages)
        keys = [stage["key"] for stage in stage_rows]
        if target not in keys or current not in keys:
            raise RecruitmentOrchestrationError("Pipeline stage template ile eşleşmiyor.")
        current_index = keys.index(current)
        target_index = keys.index(target)
        if target_index <= current_index:
            raise RecruitmentOrchestrationError("Pipeline geriye veya aynı stage üzerine taşınamaz.")
        current_stage = stage_rows[current_index]
        if target_index != current_index + 1 and not bool(current_stage.get("allow_skip")):
            raise RecruitmentOrchestrationError("Bu stage üzerinden atlama template tarafından izinli değil.")
        if target_index != current_index + 1 and not str(reason).strip():
            raise RecruitmentOrchestrationError("Stage atlamasında gerekçe zorunludur.")
        _scorecard_gate(cursor, tenant, request_id, candidate_id, current_stage)
        # READY_TO_HIRE is not only a pipeline label: accepted offer and required
        # onboarding work must already be authoritative.
        if target == "READY_TO_HIRE":
            _assert_offer_and_onboarding_ready(cursor, tenant, request_id, candidate_id)
        elapsed = max(0, int((now - entered_at).total_seconds()))
        sla_seconds = int(current_stage.get("sla_hours", 72)) * 3600
        next_revision = int(revision) + 1
        cursor.execute(
            """UPDATE recruitment.pipeline_assignments
               SET current_stage=%s,stage_entered_at=%s,revision=%s
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s AND revision=%s""",
            (target, now, next_revision, tenant, request_id, candidate_id, revision),
        )
        if cursor.rowcount != 1:
            raise RecruitmentOrchestrationError("Pipeline eşzamanlı değişiklik nedeniyle güncellenemedi.")
        event_id = uuid4()
        cursor.execute(
            """INSERT INTO recruitment.pipeline_stage_events(
                 tenant_id,event_id,request_id,candidate_id,template_id,from_stage,to_stage,
                 reason,actor,occurred_at,prior_stage_entered_at,elapsed_seconds,sla_seconds,sla_breached
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                tenant,
                event_id,
                request_id,
                candidate_id,
                template_id,
                current,
                target,
                str(reason).strip(),
                actor,
                now,
                entered_at,
                elapsed,
                sla_seconds,
                elapsed > sla_seconds,
            ),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_PIPELINE_STAGE_TRANSITIONED",
            actor,
            {
                "record_id": request_id,
                "candidate_id": candidate_id,
                "from_stage": current,
                "to_stage": target,
                "elapsed_seconds": elapsed,
                "sla_breached": elapsed > sla_seconds,
            },
        )
        database.commit()
    return candidate_orchestration_summary(request_id, candidate_id)


def submit_scorecard(
    request_id: str,
    candidate_id: str,
    *,
    competencies: dict[str, float],
    recommendation: str,
    conflict_declared: bool,
    interviewer_id: str,
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    if not 1 <= len(competencies) <= 20:
        raise RecruitmentOrchestrationError("Scorecard 1-20 competency içermelidir.")
    normalized: dict[str, float] = {}
    for key, value in competencies.items():
        label = str(key).strip()
        score = float(value)
        if not label or len(label) > 100 or score < 0 or score > 100:
            raise RecruitmentOrchestrationError("Competency score 0-100 arasında olmalıdır.")
        normalized[label] = round(score, 2)
    recommendation = str(recommendation).strip().upper()
    if recommendation not in {"STRONG_HIRE", "HIRE", "HOLD", "NO_HIRE", "STRONG_NO_HIRE"}:
        raise RecruitmentOrchestrationError("Interview recommendation desteklenmiyor.")
    overall = round(sum(normalized.values()) / len(normalized), 2)
    tenant = persistence.tenant_id()
    scorecard_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        _, stage, _, _, _ = _assignment_locked(cursor, tenant, request_id, candidate_id)
        try:
            cursor.execute(
                """INSERT INTO recruitment.interview_scorecards(
                     tenant_id,scorecard_id,request_id,candidate_id,stage,interviewer_id,
                     competencies,overall_score,recommendation,conflict_declared
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                (
                    tenant,
                    scorecard_id,
                    request_id,
                    candidate_id,
                    stage,
                    interviewer_id,
                    json.dumps(normalized, ensure_ascii=False),
                    overall,
                    recommendation,
                    bool(conflict_declared),
                ),
            )
        except Exception as error:
            raise RecruitmentOrchestrationError(
                "Aynı interviewer bu candidate/stage için daha önce scorecard göndermiş olabilir."
            ) from error
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_INTERVIEW_SCORECARD_SUBMITTED",
            interviewer_id,
            {
                "record_id": request_id,
                "candidate_id": candidate_id,
                "scorecard_id": str(scorecard_id),
                "stage": stage,
                "overall_score": overall,
                "recommendation": recommendation,
                "conflict_declared": bool(conflict_declared),
            },
        )
        database.commit()
    return {
        "scorecard_id": str(scorecard_id),
        "stage": stage,
        "overall_score": overall,
        "recommendation": recommendation,
        "conflict_declared": bool(conflict_declared),
        "immutable": True,
    }


def append_candidate_note(
    request_id: str, candidate_id: str, *, note_type: str, visibility: str, body: str, actor: str
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    note_type = str(note_type).strip().upper()
    visibility = str(visibility).strip().upper()
    text = str(body).strip()
    if note_type not in {"INTERVIEW", "PROCESS", "RISK", "FOLLOW_UP"}:
        raise RecruitmentOrchestrationError("Candidate note türü desteklenmiyor.")
    if visibility not in {"RECRUITMENT_TEAM", "HR_ONLY"}:
        raise RecruitmentOrchestrationError("Candidate note visibility geçersiz.")
    if not text or len(text) > 4000:
        raise RecruitmentOrchestrationError("Candidate note 1-4000 karakter olmalıdır.")
    note_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """INSERT INTO recruitment.candidate_notes(
                 tenant_id,note_id,request_id,candidate_id,note_type,visibility,body,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (persistence.tenant_id(), note_id, request_id, candidate_id, note_type, visibility, text, actor),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_CANDIDATE_NOTE_APPENDED",
            actor,
            {"record_id": request_id, "candidate_id": candidate_id, "note_id": str(note_id), "note_type": note_type, "visibility": visibility},
        )
        database.commit()
    return {"note_id": str(note_id), "note_type": note_type, "visibility": visibility, "created_by": actor, "immutable": True}


def _canonical_offer_package(package: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    allowed = {
        "country_code", "locale", "position", "employment_type", "work_location",
        "employment_start", "currency", "compensation_amount", "compensation_period",
        "probation_summary", "benefits_summary", "agreement_template_key",
    }
    normalized = {key: package[key] for key in sorted(package) if key in allowed}
    required = {"country_code", "position", "employment_type", "employment_start", "currency", "compensation_amount"}
    if not required.issubset(normalized):
        raise RecruitmentOrchestrationError("Offer package zorunlu alanları eksik.")
    normalized["country_code"] = str(normalized["country_code"]).strip().upper()
    normalized["currency"] = str(normalized["currency"]).strip().upper()
    if len(normalized["country_code"]) != 2 or len(normalized["currency"]) != 3:
        raise RecruitmentOrchestrationError("Offer country/currency kodu geçersiz.")
    amount = float(normalized["compensation_amount"])
    if amount <= 0 or amount > 1_000_000_000:
        raise RecruitmentOrchestrationError("Offer compensation amount geçersiz.")
    normalized["compensation_amount"] = round(amount, 2)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return normalized, sha256(raw).digest()


def create_offer(
    request_id: str,
    candidate_id: str,
    *,
    package: dict[str, Any],
    expires_in_hours: int,
    actor: str,
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    if expires_in_hours < 1 or expires_in_hours > 24 * 30:
        raise RecruitmentOrchestrationError("Offer validity 1 saat ile 30 gün arasında olmalıdır.")
    normalized, digest = _canonical_offer_package(package)
    tenant = persistence.tenant_id()
    offer_id = uuid4()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        _, current_stage, _, _, _ = _assignment_locked(cursor, tenant, request_id, candidate_id)
        if current_stage != "OFFER":
            raise RecruitmentOrchestrationError("Offer yalnız OFFER pipeline stage içinde oluşturulabilir.")
        cursor.execute(
            "SELECT COALESCE(max(version),0)+1 FROM recruitment.offer_packages WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s",
            (tenant, request_id, candidate_id),
        )
        version = int(cursor.fetchone()[0])
        cursor.execute(
            """INSERT INTO recruitment.offer_packages(
                 tenant_id,offer_id,request_id,candidate_id,version,package_sha256,package,expires_at,created_at,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (
                tenant,
                offer_id,
                request_id,
                candidate_id,
                version,
                digest,
                json.dumps(normalized, ensure_ascii=False),
                now + timedelta(hours=expires_in_hours),
                now,
                actor,
            ),
        )
        cursor.execute(
            """INSERT INTO recruitment.offer_events(
                 tenant_id,event_id,offer_id,request_id,candidate_id,decision,actor_type,actor_ref,occurred_at,metadata
               ) VALUES(%s,%s,%s,%s,%s,'ISSUED','HR',%s,%s,%s::jsonb)""",
            (
                tenant,
                uuid4(),
                offer_id,
                request_id,
                candidate_id,
                actor,
                now,
                json.dumps({"version": version, "package_sha256": digest.hex()}),
            ),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_OFFER_ISSUED",
            actor,
            {"record_id": request_id, "candidate_id": candidate_id, "offer_id": str(offer_id), "version": version, "package_sha256": digest.hex()},
        )
        database.commit()
    return {
        "offer_id": str(offer_id),
        "version": version,
        "package_sha256": digest.hex(),
        "expires_at": (now + timedelta(hours=expires_in_hours)).isoformat(),
        "signature_truth_boundary": "CANDIDATE_DECISION_RECORD_NOT_QUALIFIED_E_SIGNATURE",
        "immutable": True,
    }


def issue_offer_decision_capability(offer_id: str, *, expires_in_hours: int, actor: str) -> dict:
    _ensure_ready()
    if expires_in_hours < 1 or expires_in_hours > 24 * 30:
        raise RecruitmentOrchestrationError("Offer decision capability validity geçersiz.")
    try:
        offer_uuid = UUID(str(offer_id))
    except ValueError as error:
        raise RecruitmentOrchestrationError("Offer kimliği geçersiz.") from error
    token = secrets.token_urlsafe(40)
    digest = sha256(token.encode("utf-8")).digest()
    capability_id = uuid4()
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT request_id,candidate_id,expires_at FROM recruitment.offer_packages WHERE tenant_id=%s AND offer_id=%s",
            (tenant, offer_uuid),
        )
        offer = cursor.fetchone()
        if offer is None:
            raise RecruitmentOrchestrationError("Offer bulunamadı.")
        request_id, candidate_id, offer_expires = offer
        cursor.execute(
            "SELECT decision FROM recruitment.offer_events WHERE tenant_id=%s AND offer_id=%s ORDER BY occurred_at DESC,event_id DESC LIMIT 1",
            (tenant, offer_uuid),
        )
        latest = cursor.fetchone()
        if latest and latest[0] in _TERMINAL_OFFER_EVENTS:
            raise RecruitmentOrchestrationError("Offer terminal state içinde; yeni capability verilemez.")
        expires_at = min(offer_expires, now + timedelta(hours=expires_in_hours))
        if expires_at <= now:
            raise RecruitmentOrchestrationError("Offer süresi dolmuş.")
        cursor.execute(
            """INSERT INTO recruitment.offer_decision_capabilities(
                 tenant_id,capability_id,offer_id,token_sha256,expires_at,issued_at,issued_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (tenant, capability_id, offer_uuid, digest, expires_at, now, actor),
        )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_OFFER_DECISION_CAPABILITY_ISSUED",
            actor,
            {"record_id": request_id, "candidate_id": candidate_id, "offer_id": str(offer_uuid), "capability_id": str(capability_id)},
        )
        database.commit()
    return {
        "capability": token,
        "capability_id": str(capability_id),
        "offer_id": str(offer_uuid),
        "expires_at": expires_at.isoformat(),
        "max_uses": 1,
    }


def _create_default_onboarding_tasks(cursor, tenant: str, request_id: str, candidate_id: str, offer_id: UUID, now: datetime) -> None:
    for task in _DEFAULT_ONBOARDING_TASKS:
        cursor.execute(
            """INSERT INTO recruitment.onboarding_tasks(
                 tenant_id,task_id,request_id,candidate_id,offer_id,task_key,title,owner_role,
                 required,due_at,dependencies,status,revision
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'PENDING',1)
               ON CONFLICT (tenant_id,request_id,candidate_id,offer_id,task_key) DO NOTHING""",
            (
                tenant,
                uuid4(),
                request_id,
                candidate_id,
                offer_id,
                task["task_key"],
                task["title"],
                task["owner_role"],
                task["required"],
                now + timedelta(hours=int(task["due_hours"])),
                json.dumps(task["dependencies"]),
            ),
        )


def decide_offer_with_capability(raw_token: str, decision: str) -> dict:
    _ensure_ready()
    token = str(raw_token or "").strip()
    normalized_decision = str(decision).strip().upper()
    if len(token) < 40 or len(token) > 256 or normalized_decision not in {"ACCEPTED", "DECLINED"}:
        raise RecruitmentOrchestrationError("Offer decision capability geçersiz veya süresi dolmuş.")
    digest = sha256(token.encode("utf-8")).digest()
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT capability_id,offer_id,expires_at,consumed_at
               FROM recruitment.offer_decision_capabilities
               WHERE tenant_id=%s AND token_sha256=%s FOR UPDATE""",
            (tenant, digest),
        )
        capability = cursor.fetchone()
        if capability is None:
            raise RecruitmentOrchestrationError("Offer decision capability geçersiz veya süresi dolmuş.")
        capability_id, offer_id, expires_at, consumed_at = capability
        if consumed_at is not None or expires_at <= now:
            raise RecruitmentOrchestrationError("Offer decision capability geçersiz veya süresi dolmuş.")
        cursor.execute(
            "SELECT request_id,candidate_id,expires_at FROM recruitment.offer_packages WHERE tenant_id=%s AND offer_id=%s",
            (tenant, offer_id),
        )
        offer = cursor.fetchone()
        if offer is None:
            raise RecruitmentOrchestrationError("Offer decision capability geçersiz veya süresi dolmuş.")
        request_id, candidate_id, offer_expires = offer
        if offer_expires <= now:
            raise RecruitmentOrchestrationError("Offer süresi dolmuş.")
        cursor.execute(
            "SELECT decision FROM recruitment.offer_events WHERE tenant_id=%s AND offer_id=%s ORDER BY occurred_at DESC,event_id DESC LIMIT 1",
            (tenant, offer_id),
        )
        latest = cursor.fetchone()
        if latest and latest[0] in _TERMINAL_OFFER_EVENTS:
            raise RecruitmentOrchestrationError("Offer daha önce sonuçlandırılmış.")
        cursor.execute(
            """UPDATE recruitment.offer_decision_capabilities
               SET consumed_at=%s,consumed_decision=%s
               WHERE tenant_id=%s AND capability_id=%s AND consumed_at IS NULL""",
            (now, normalized_decision, tenant, capability_id),
        )
        if cursor.rowcount != 1:
            raise RecruitmentOrchestrationError("Offer decision replay reddedildi.")
        cursor.execute(
            """INSERT INTO recruitment.offer_events(
                 tenant_id,event_id,offer_id,request_id,candidate_id,decision,
                 actor_type,actor_ref,occurred_at,metadata
               ) VALUES(%s,%s,%s,%s,%s,%s,'CANDIDATE_CAPABILITY',%s,%s,%s::jsonb)""",
            (
                tenant,
                uuid4(),
                offer_id,
                request_id,
                candidate_id,
                normalized_decision,
                str(capability_id),
                now,
                json.dumps({"capability_id": str(capability_id)}),
            ),
        )
        if normalized_decision == "ACCEPTED":
            _create_default_onboarding_tasks(cursor, tenant, request_id, candidate_id, offer_id, now)
        persistence._build_audit_record(
            cursor,
            f"RECRUITMENT_OFFER_{normalized_decision}",
            f"candidate-capability:{capability_id}",
            {"record_id": request_id, "candidate_id": candidate_id, "offer_id": str(offer_id)},
        )
        database.commit()
    return {
        "accepted": True,
        "decision": normalized_decision,
        "offer_id": str(offer_id),
        "truth_boundary": "ONE_TIME_CANDIDATE_DECISION_NOT_QUALIFIED_E_SIGNATURE",
        "onboarding_created": normalized_decision == "ACCEPTED",
    }


def get_offer_by_capability(raw_token: str) -> dict:
    _ensure_ready()
    token = str(raw_token or "").strip()
    if len(token) < 40 or len(token) > 256:
        raise RecruitmentOrchestrationError("Offer capability geçersiz veya süresi dolmuş.")
    digest = sha256(token.encode("utf-8")).digest()
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT p.offer_id,p.package,p.package_sha256,p.expires_at,c.consumed_at
               FROM recruitment.offer_decision_capabilities c
               JOIN recruitment.offer_packages p
                 ON p.tenant_id=c.tenant_id AND p.offer_id=c.offer_id
               WHERE c.tenant_id=%s AND c.token_sha256=%s""",
            (tenant, digest),
        )
        row = cursor.fetchone()
        if row is None or row[3] <= now:
            raise RecruitmentOrchestrationError("Offer capability geçersiz veya süresi dolmuş.")
        offer_id, package, package_digest, expires_at, consumed_at = row
        return {
            "offer_id": str(offer_id),
            "package": package,
            "package_sha256": bytes(package_digest).hex(),
            "expires_at": expires_at.isoformat(),
            "decision_available": consumed_at is None,
            "signature_truth_boundary": "CANDIDATE_DECISION_RECORD_NOT_QUALIFIED_E_SIGNATURE",
        }


def update_onboarding_task(
    task_id: str, *, status: str, note: str, actor: str
) -> dict:
    _ensure_ready()
    try:
        task_uuid = UUID(str(task_id))
    except ValueError as error:
        raise RecruitmentOrchestrationError("Onboarding task kimliği geçersiz.") from error
    target = str(status).strip().upper()
    if target not in {"IN_PROGRESS", "BLOCKED", "COMPLETED", "WAIVED"}:
        raise RecruitmentOrchestrationError("Onboarding task status geçersiz.")
    if target == "WAIVED" and not str(note).strip():
        raise RecruitmentOrchestrationError("Required task waiver gerekçesi zorunludur.")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,candidate_id,offer_id,task_key,dependencies,status,revision
               FROM recruitment.onboarding_tasks
               WHERE tenant_id=%s AND task_id=%s FOR UPDATE""",
            (tenant, task_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentOrchestrationError("Onboarding task bulunamadı.")
        request_id, candidate_id, offer_id, task_key, dependencies, current_status, revision = row
        if current_status in {"COMPLETED", "WAIVED"}:
            raise RecruitmentOrchestrationError("Terminal onboarding task tekrar değiştirilemez.")
        if target == "COMPLETED" and dependencies:
            cursor.execute(
                """SELECT task_key,status FROM recruitment.onboarding_tasks
                   WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s AND offer_id=%s
                     AND task_key=ANY(%s)""",
                (tenant, request_id, candidate_id, offer_id, list(dependencies)),
            )
            states = {key: state for key, state in cursor.fetchall()}
            missing = [dep for dep in dependencies if states.get(dep) not in {"COMPLETED", "WAIVED"}]
            if missing:
                raise RecruitmentOrchestrationError(
                    f"Task dependencies tamamlanmadı: {', '.join(missing)}"
                )
        next_revision = int(revision) + 1
        cursor.execute(
            """UPDATE recruitment.onboarding_tasks
               SET status=%s,revision=%s,completed_at=%s,completed_by=%s,completion_note=%s
               WHERE tenant_id=%s AND task_id=%s AND revision=%s""",
            (
                target,
                next_revision,
                now if target in {"COMPLETED", "WAIVED"} else None,
                actor if target in {"COMPLETED", "WAIVED"} else None,
                str(note).strip() or None,
                tenant,
                task_uuid,
                revision,
            ),
        )
        if cursor.rowcount != 1:
            raise RecruitmentOrchestrationError("Onboarding task concurrent update nedeniyle reddedildi.")
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_ONBOARDING_TASK_UPDATED",
            actor,
            {"record_id": request_id, "candidate_id": candidate_id, "task_id": str(task_uuid), "task_key": task_key, "status": target},
        )
        database.commit()
    return {"task_id": str(task_uuid), "task_key": task_key, "status": target, "revision": next_revision}


def _assert_offer_and_onboarding_ready(cursor, tenant: str, request_id: str, candidate_id: str) -> UUID:
    cursor.execute(
        """SELECT p.offer_id
           FROM recruitment.offer_packages p
           JOIN LATERAL (
             SELECT e.decision FROM recruitment.offer_events e
             WHERE e.tenant_id=p.tenant_id AND e.offer_id=p.offer_id
             ORDER BY e.occurred_at DESC,e.event_id DESC LIMIT 1
           ) latest ON true
           WHERE p.tenant_id=%s AND p.request_id=%s AND p.candidate_id=%s
             AND latest.decision='ACCEPTED'
           ORDER BY p.version DESC LIMIT 1""",
        (tenant, request_id, candidate_id),
    )
    offer = cursor.fetchone()
    if offer is None:
        raise RecruitmentOrchestrationError("READY_TO_HIRE için accepted offer zorunludur.")
    offer_id = offer[0]
    cursor.execute(
        """SELECT count(*) FILTER (WHERE required),
                  count(*) FILTER (WHERE required AND status IN ('COMPLETED','WAIVED'))
           FROM recruitment.onboarding_tasks
           WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s AND offer_id=%s""",
        (tenant, request_id, candidate_id, offer_id),
    )
    required, finished = cursor.fetchone()
    if int(required) == 0 or int(required) != int(finished):
        raise RecruitmentOrchestrationError(
            f"READY_TO_HIRE için required onboarding tasks tamamlanmalı ({finished}/{required})."
        )
    return offer_id


def require_hire_ready(request_id: str, candidate_id: str) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        template_id, stage, entered_at, revision, _ = _assignment_locked(
            cursor, tenant, request_id, candidate_id
        )
        if stage != "READY_TO_HIRE":
            raise RecruitmentOrchestrationError("Candidate pipeline READY_TO_HIRE stage içinde değil.")
        offer_id = _assert_offer_and_onboarding_ready(cursor, tenant, request_id, candidate_id)
        database.rollback()
    return {
        "ready": True,
        "request_id": request_id,
        "candidate_id": candidate_id,
        "template_id": str(template_id),
        "pipeline_stage": stage,
        "pipeline_revision": int(revision),
        "stage_entered_at": entered_at.isoformat(),
        "accepted_offer_id": str(offer_id),
        "truth_boundary": "PIPELINE_PLUS_ACCEPTED_OFFER_PLUS_REQUIRED_ONBOARDING",
    }


def candidate_orchestration_summary(request_id: str, candidate_id: str) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT a.template_id,a.current_stage,a.stage_entered_at,a.revision,t.template_key,t.version,t.name,t.stages
               FROM recruitment.pipeline_assignments a
               JOIN recruitment.pipeline_templates t ON t.tenant_id=a.tenant_id AND t.template_id=a.template_id
               WHERE a.tenant_id=%s AND a.request_id=%s AND a.candidate_id=%s""",
            (tenant, request_id, candidate_id),
        )
        assignment = cursor.fetchone()
        pipeline = None
        if assignment:
            template_id, stage, entered_at, revision, template_key, version, name, stages = assignment
            stage_cfg = next((item for item in stages if item["key"] == stage), None) or {}
            elapsed = max(0, int((now - entered_at).total_seconds()))
            sla_seconds = int(stage_cfg.get("sla_hours", 72)) * 3600
            pipeline = {
                "template_id": str(template_id),
                "template_key": template_key,
                "template_version": int(version),
                "template_name": name,
                "current_stage": stage,
                "stage_entered_at": entered_at.isoformat(),
                "stage_elapsed_seconds": elapsed,
                "stage_sla_seconds": sla_seconds,
                "stage_sla_breached": elapsed > sla_seconds,
                "revision": int(revision),
            }
        cursor.execute(
            """SELECT stage,count(*),round(avg(overall_score)::numeric,2)
               FROM recruitment.interview_scorecards
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s
               GROUP BY stage ORDER BY stage""",
            (tenant, request_id, candidate_id),
        )
        scorecards = [
            {"stage": row[0], "count": int(row[1]), "average_score": float(row[2])}
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """SELECT p.offer_id,p.version,p.package_sha256,p.expires_at,
                      (SELECT e.decision FROM recruitment.offer_events e
                       WHERE e.tenant_id=p.tenant_id AND e.offer_id=p.offer_id
                       ORDER BY e.occurred_at DESC,e.event_id DESC LIMIT 1)
               FROM recruitment.offer_packages p
               WHERE p.tenant_id=%s AND p.request_id=%s AND p.candidate_id=%s
               ORDER BY p.version DESC""",
            (tenant, request_id, candidate_id),
        )
        offers = [
            {
                "offer_id": str(row[0]),
                "version": int(row[1]),
                "package_sha256": bytes(row[2]).hex(),
                "expires_at": row[3].isoformat(),
                "state": row[4],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """SELECT task_id,task_key,title,owner_role,required,due_at,dependencies,status,revision
               FROM recruitment.onboarding_tasks
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s
               ORDER BY created_at,task_key""",
            (tenant, request_id, candidate_id),
        )
        tasks = [
            {
                "task_id": str(row[0]),
                "task_key": row[1],
                "title": row[2],
                "owner_role": row[3],
                "required": bool(row[4]),
                "due_at": row[5].isoformat() if row[5] else None,
                "dependencies": row[6],
                "status": row[7],
                "revision": int(row[8]),
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """SELECT note_id,note_type,visibility,created_at,created_by
               FROM recruitment.candidate_notes
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s
               ORDER BY created_at DESC LIMIT 50""",
            (tenant, request_id, candidate_id),
        )
        notes = [
            {"note_id": str(row[0]), "note_type": row[1], "visibility": row[2], "created_at": row[3].isoformat(), "created_by": row[4]}
            for row in cursor.fetchall()
        ]
        database.rollback()
    return {
        "request_id": request_id,
        "candidate_id": candidate_id,
        "pipeline": pipeline,
        "scorecards": scorecards,
        "offers": offers,
        "onboarding_tasks": tasks,
        "notes": notes,
    }


def funnel_analytics() -> dict:
    _ensure_ready()
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT current_stage,count(*),
                      round(avg(extract(epoch from (clock_timestamp()-stage_entered_at)))::numeric,0)
               FROM recruitment.pipeline_assignments
               WHERE tenant_id=%s GROUP BY current_stage ORDER BY count(*) DESC,current_stage""",
            (tenant,),
        )
        stages = [
            {"stage": row[0], "candidates": int(row[1]), "average_stage_age_seconds": int(row[2] or 0)}
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """SELECT decision,count(*) FROM recruitment.offer_events
               WHERE tenant_id=%s AND decision IN ('ACCEPTED','DECLINED','EXPIRED','WITHDRAWN')
               GROUP BY decision""",
            (tenant,),
        )
        offers = {row[0]: int(row[1]) for row in cursor.fetchall()}
        cursor.execute(
            """SELECT owner_role,status,count(*) FROM recruitment.onboarding_tasks
               WHERE tenant_id=%s GROUP BY owner_role,status ORDER BY owner_role,status""",
            (tenant,),
        )
        onboarding = [
            {"owner_role": row[0], "status": row[1], "count": int(row[2])}
            for row in cursor.fetchall()
        ]
        database.rollback()
    return {"pipeline_stages": stages, "offer_outcomes": offers, "onboarding": onboarding}
