from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


_SUPPORTED_METRICS = frozenset({"nsfr", "pfr", "refund", "prep", "picking", "otp", "putaway"})


@dataclass(frozen=True)
class KpiRegistryPromotionDecision:
    metric: str
    query_id: str
    review_artifact_fingerprint: str
    query_template_fingerprint: str
    schema_fingerprint: str
    promotion_reference: str
    reviewer: str
    reviewed_at: str
    approved_for_registry_change: bool = True
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "query_id": self.query_id,
            "review_artifact_fingerprint": self.review_artifact_fingerprint,
            "query_template_fingerprint": self.query_template_fingerprint,
            "schema_fingerprint": self.schema_fingerprint,
            "promotion_reference": self.promotion_reference,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "approved_for_registry_change": self.approved_for_registry_change,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# Deliberately empty until a real, human-reviewed promotion decision is checked into
# the repository. A random 64-character value in KPI_REGISTRY is therefore insufficient
# to make a new KPI executable. The exact decision object must be independently present
# here and must still match the pinned metric/query/template/schema/review-artifact
# lineage at runtime.
APPROVED_KPI_REGISTRY_PROMOTIONS: dict[str, KpiRegistryPromotionDecision] = {}


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_registry_promotion_invalid_fingerprint:{field}")
    return text


def _review_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("kpi_registry_promotion_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_registry_promotion_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_registry_promotion_future_review_time")
    return value


def _artifact_field(artifact: object, field: str) -> object:
    if isinstance(artifact, Mapping):
        return artifact.get(field)
    return getattr(artifact, field, None)


def seal_kpi_registry_promotion(
    *,
    metric: str,
    query_id: str,
    review_artifact: object,
    query_template_fingerprint: str,
    schema_fingerprint: str,
    promotion_reference: str,
    reviewer: str,
    reviewed_at: str,
) -> KpiRegistryPromotionDecision:
    """Authorize a reviewed registry change without making the KPI executable."""

    if metric not in _SUPPORTED_METRICS:
        raise ValueError("kpi_registry_promotion_unsupported_metric")
    if not query_id.strip():
        raise ValueError("kpi_registry_promotion_query_id_required")
    if not promotion_reference.strip() or not reviewer.strip():
        raise ValueError("kpi_registry_promotion_human_approval_required")
    _review_time(reviewed_at)

    if _artifact_field(review_artifact, "approved_for_registry_review") is not True:
        raise ValueError("kpi_registry_promotion_review_artifact_not_approved")
    if _artifact_field(review_artifact, "executable") is not False:
        raise ValueError("kpi_registry_promotion_review_artifact_must_be_non_executable")

    artifact_metric = _artifact_field(review_artifact, "metric")
    if artifact_metric is not None and artifact_metric != metric:
        raise ValueError("kpi_registry_promotion_artifact_metric_mismatch")

    artifact_fp = _artifact_field(review_artifact, "fingerprint")
    if callable(artifact_fp):
        artifact_fp = artifact_fp()
    artifact_fp = _sha(artifact_fp, "review_artifact")

    pinned_schema = _artifact_field(review_artifact, "schema_fingerprint")
    if pinned_schema is None:
        pinned_schema = _artifact_field(review_artifact, "schema_evidence_fingerprint")
    pinned_schema = _sha(pinned_schema, "artifact_schema")
    requested_schema = _sha(schema_fingerprint, "schema")
    if pinned_schema != requested_schema:
        raise ValueError("kpi_registry_promotion_schema_mismatch")

    template_fp = _sha(query_template_fingerprint, "query_template")

    return KpiRegistryPromotionDecision(
        metric=metric,
        query_id=query_id.strip(),
        review_artifact_fingerprint=artifact_fp,
        query_template_fingerprint=template_fp,
        schema_fingerprint=requested_schema,
        promotion_reference=promotion_reference.strip(),
        reviewer=reviewer.strip(),
        reviewed_at=reviewed_at,
        approved_for_registry_change=True,
        executable=False,
    )


def verify_registered_kpi_promotion(
    *,
    promotion_fingerprint: str,
    metric: str,
    query_id: str,
    query_template_fingerprint: str,
    schema_fingerprint: str,
    review_artifact_fingerprint: str,
    promotions: Mapping[str, KpiRegistryPromotionDecision] = APPROVED_KPI_REGISTRY_PROMOTIONS,
) -> KpiRegistryPromotionDecision:
    """Require the exact sealed promotion object and its complete reviewed lineage."""

    fingerprint = _sha(promotion_fingerprint, "registered_promotion")
    decision = promotions.get(fingerprint)
    if decision is None:
        raise ValueError(f"kpi_registry_promotion_decision_not_registered:{metric}")
    if decision.fingerprint != fingerprint:
        raise ValueError(f"kpi_registry_promotion_decision_fingerprint_drift:{metric}")
    if decision.approved_for_registry_change is not True or decision.executable is not False:
        raise ValueError(f"kpi_registry_promotion_decision_state_invalid:{metric}")
    if decision.metric != metric:
        raise ValueError(f"kpi_registry_promotion_decision_metric_mismatch:{metric}")
    if decision.query_id != query_id:
        raise ValueError(f"kpi_registry_promotion_decision_query_mismatch:{metric}")
    if decision.query_template_fingerprint != _sha(query_template_fingerprint, "registered_template"):
        raise ValueError(f"kpi_registry_promotion_decision_template_drift:{metric}")
    if decision.schema_fingerprint != _sha(schema_fingerprint, "registered_schema"):
        raise ValueError(f"kpi_registry_promotion_decision_schema_drift:{metric}")
    if decision.review_artifact_fingerprint != _sha(
        review_artifact_fingerprint, "registered_review_artifact"
    ):
        raise ValueError(f"kpi_registry_promotion_decision_review_artifact_drift:{metric}")
    return decision
