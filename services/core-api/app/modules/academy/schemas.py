from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

Locale = Literal["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"]
ContentType = Literal[
    "document",
    "video",
    "sop",
    "interactive",
    "live",
    "announcement",
    "poster",
    "survey",
]
PublicationStatus = Literal["draft", "published", "retired"]
SUPPORTED_LOCALES = {"tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"}


def _validate_i18n(value: dict[str, str], *, required: bool = True) -> dict[str, str]:
    invalid = set(value) - SUPPORTED_LOCALES
    if invalid:
        raise ValueError(f"Unsupported locales: {', '.join(sorted(invalid))}")
    normalized = {
        key: text.strip() for key, text in value.items() if isinstance(text, str) and text.strip()
    }
    if required and not normalized:
        raise ValueError("At least one non-empty localized value is required")
    return normalized


class ContentCreateRequest(BaseModel):
    content_type: ContentType
    slug: str = Field(min_length=2, max_length=180, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title_i18n: dict[str, str]
    description_i18n: dict[str, str] = Field(default_factory=dict)
    version_label: str = Field(min_length=1, max_length=80)
    locale: Locale = "tr"
    mime_type: str | None = Field(default=None, max_length=160)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    storage_key: str | None = Field(default=None, max_length=1024)
    delivery_key: str | None = Field(default=None, max_length=512)
    size_bytes: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    accessibility_metadata: dict[str, object] = Field(default_factory=dict)
    status: PublicationStatus = "draft"

    @field_validator("title_i18n")
    @classmethod
    def validate_title_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)

    @field_validator("description_i18n")
    @classmethod
    def validate_description_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)


class ContentVersionCreateRequest(BaseModel):
    version_label: str = Field(min_length=1, max_length=80)
    locale: Locale = "tr"
    mime_type: str | None = Field(default=None, max_length=160)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    storage_key: str | None = Field(default=None, max_length=1024)
    delivery_key: str | None = Field(default=None, max_length=512)
    size_bytes: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    accessibility_metadata: dict[str, object] = Field(default_factory=dict)
    status: PublicationStatus = "draft"


class MediaAssetCreateRequest(BaseModel):
    content_version_id: UUID
    asset_kind: Literal["video_hls", "video_dash", "document"]
    storage_provider: Literal["s3", "gcs", "azure", "minio"]
    storage_bucket: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=1024)
    delivery_key: str = Field(min_length=1, max_length=512)
    manifest_path: str | None = Field(default=None, max_length=512)
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    size_bytes: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    transcode_status: Literal["pending", "ready", "failed", "retired"] = "ready"
    delivery_mode: Literal["hls", "dash", "document"] = "hls"
    encryption_mode: str = Field(default="edge_token", min_length=1, max_length=30)
    segment_duration_seconds: int = Field(default=6, ge=2, le=12)


class PathItemCreate(BaseModel):
    content_version_id: UUID
    required: bool = True
    completion_policy: dict[str, object] = Field(default_factory=dict)


class PathRoleAssignmentCreate(BaseModel):
    role_key: str = Field(min_length=1, max_length=160)
    required: bool = True
    due_days: int | None = Field(default=None, ge=0, le=3650)


class LearningPathCreateRequest(BaseModel):
    key: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title_i18n: dict[str, str]
    description_i18n: dict[str, str] = Field(default_factory=dict)
    certificate_enabled: bool = True
    completion_policy: dict[str, object] = Field(
        default_factory=lambda: {"required_progress_percent": 90, "required_quizzes": True}
    )
    items: list[PathItemCreate] = Field(min_length=1, max_length=500)
    role_assignments: list[PathRoleAssignmentCreate] = Field(default_factory=list, max_length=200)
    status: PublicationStatus = "draft"

    @field_validator("title_i18n")
    @classmethod
    def validate_title_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)

    @field_validator("description_i18n")
    @classmethod
    def validate_description_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)


class QuestionOptionCreate(BaseModel):
    label_i18n: dict[str, str]
    is_correct: bool = False

    @field_validator("label_i18n")
    @classmethod
    def validate_label_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)


class QuestionCreate(BaseModel):
    question_type: Literal["single_choice", "multiple_choice", "true_false"]
    prompt_i18n: dict[str, str]
    points: float = Field(default=1, gt=0, le=1000)
    required: bool = True
    options: list[QuestionOptionCreate] = Field(min_length=2, max_length=20)

    @field_validator("prompt_i18n")
    @classmethod
    def validate_prompt_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)

    @model_validator(mode="after")
    def validate_correct_answers(self) -> "QuestionCreate":
        correct_count = sum(1 for option in self.options if option.is_correct)
        if self.question_type in {"single_choice", "true_false"} and correct_count != 1:
            raise ValueError(
                "Single-choice and true/false questions require exactly one correct option"
            )
        if self.question_type == "multiple_choice" and correct_count < 1:
            raise ValueError("Multiple-choice questions require at least one correct option")
        return self


class QuizCreateRequest(BaseModel):
    content_version_id: UUID
    kind: Literal["checkpoint", "completion"] = "completion"
    checkpoint_at_ms: int | None = Field(default=None, ge=0)
    pass_score: float = Field(default=80, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=1, le=100)
    required: bool = True
    status: PublicationStatus = "draft"
    supersedes_quiz_id: UUID | None = None
    questions: list[QuestionCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "QuizCreateRequest":
        if self.kind == "checkpoint" and self.checkpoint_at_ms is None:
            raise ValueError("Checkpoint quizzes require checkpoint_at_ms")
        if self.kind == "completion" and self.checkpoint_at_ms is not None:
            raise ValueError("Completion quizzes cannot define checkpoint_at_ms")
        return self


class EntitlementCreateRequest(BaseModel):
    resource_type: Literal["content", "path"]
    resource_id: UUID
    principal_type: Literal["role", "subject"]
    principal_key: str = Field(min_length=1, max_length=255)
    permission: Literal["view", "learn", "manage"] = "learn"
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ManualEnrollmentRequest(BaseModel):
    path_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    due_at: datetime | None = None


class ProgressUpdateRequest(BaseModel):
    content_version_id: UUID
    last_position_ms: int = Field(default=0, ge=0)
    watched_delta_ms: int = Field(default=0, ge=0, le=300_000)
    complete_requested: bool = False
    expected_revision: int | None = Field(default=None, ge=0)


class QuizAnswerRequest(BaseModel):
    question_id: UUID
    selected_option_ids: list[UUID] = Field(min_length=1, max_length=20)


class QuizAttemptRequest(BaseModel):
    enrollment_id: UUID
    answers: list[QuizAnswerRequest] = Field(min_length=1, max_length=200)


class CertificateRevocationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class DocumentChunkCreate(BaseModel):
    chunk_ordinal: int = Field(ge=1)
    locale: Locale
    heading: str | None = Field(default=None, max_length=500)
    text_content: str = Field(min_length=1, max_length=20_000)
    source_page: int | None = Field(default=None, ge=1)
    source_anchor: str | None = Field(default=None, max_length=500)
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentIngestRequest(BaseModel):
    content_version_id: UUID
    chunks: list[DocumentChunkCreate] = Field(min_length=1, max_length=10_000)


class QuestionAnswerRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    locale: Locale = "tr"
    top_k: int = Field(default=5, ge=1, le=10)


class PlaybackAuthorization(BaseModel):
    playback_url: str
    authorization_token: str
    expires_in_seconds: int
    content_version_id: UUID
    cache_policy: str = "private-manifest, public-cacheable-segments-with-edge-auth"
    download_protection: str = "friction-not-guarantee"


class CompletionResponse(BaseModel):
    enrollment_id: UUID
    status: Literal["completed"]
    certificate_code: str | None
    contract_version: str | None
    completion_fingerprint: str | None
