from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from app.core.localization import canonicalize_content_locale


def _validate_locale(value: str) -> str:
    canonical = canonicalize_content_locale(value)
    if canonical is None:
        raise ValueError("Unsupported locale")
    return canonical


Locale = Annotated[str, AfterValidator(_validate_locale)]
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


def _validate_i18n(value: dict[str, str], *, required: bool = True) -> dict[str, str]:
    normalized: dict[str, str] = {}
    unsupported: list[str] = []

    for raw_locale, raw_text in value.items():
        locale = canonicalize_content_locale(raw_locale)
        if locale is None:
            unsupported.append(raw_locale)
            continue
        if locale in normalized:
            raise ValueError(
                f"Duplicate locale after normalization: {raw_locale} resolves to {locale}"
            )
        if isinstance(raw_text, str) and raw_text.strip():
            normalized[locale] = raw_text.strip()

    if unsupported:
        raise ValueError(f"Unsupported locales: {', '.join(sorted(unsupported))}")
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


class PlaybackHeartbeatRequest(BaseModel):
    sequence_no: int = Field(ge=1)
    from_position_ms: int = Field(ge=0)
    to_position_ms: int = Field(ge=0)
    client_elapsed_ms: int = Field(ge=0, le=60_000)
    playback_rate: float = Field(default=1.0, ge=0.25, le=4.0)
    visibility: Literal["visible", "hidden", "picture_in_picture"] = "visible"

    @model_validator(mode="after")
    def validate_positions(self) -> "PlaybackHeartbeatRequest":
        if self.to_position_ms < self.from_position_ms:
            raise ValueError("Heartbeat to_position_ms cannot be before from_position_ms")
        return self


class InteractionNodeCreate(BaseModel):
    node_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    node_type: Literal[
        "checkpoint",
        "hotspot",
        "single_choice",
        "multiple_choice",
        "drag_drop",
        "overlay",
        "reflection",
        "branch",
        "cta",
    ]
    at_ms: int = Field(ge=0)
    blocking: bool = False
    required: bool = False
    score_weight: float = Field(default=0, ge=0, le=1000)
    payload: dict[str, object] = Field(default_factory=dict)


class InteractionSetCreateRequest(BaseModel):
    content_version_id: UUID
    version_number: int = Field(ge=1)
    title_i18n: dict[str, str] = Field(default_factory=dict)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    nodes: list[InteractionNodeCreate] = Field(min_length=1, max_length=1000)
    status: PublicationStatus = "draft"

    @field_validator("title_i18n")
    @classmethod
    def validate_title_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)

    @model_validator(mode="after")
    def validate_unique_node_keys(self) -> "InteractionSetCreateRequest":
        keys = [node.node_key for node in self.nodes]
        if len(keys) != len(set(keys)):
            raise ValueError("Interaction node_key values must be unique within a set")
        return self


class ScenarioNodeCreate(BaseModel):
    node_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    node_type: Literal["scene", "decision", "task", "evidence", "outcome"]
    prompt_i18n: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, object] = Field(default_factory=dict)
    terminal: bool = False
    terminal_outcome: Literal["completed", "failed", "remediation"] | None = None

    @field_validator("prompt_i18n")
    @classmethod
    def validate_prompt_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)

    @model_validator(mode="after")
    def validate_terminal_outcome(self) -> "ScenarioNodeCreate":
        if self.terminal and self.terminal_outcome is None:
            raise ValueError("Terminal scenario nodes require terminal_outcome")
        if not self.terminal and self.terminal_outcome is not None:
            raise ValueError("Non-terminal scenario nodes cannot define terminal_outcome")
        return self


class ScenarioEdgeCreate(BaseModel):
    from_node_key: str = Field(min_length=1, max_length=120)
    choice_key: str = Field(min_length=1, max_length=120)
    to_node_key: str = Field(min_length=1, max_length=120)
    label_i18n: dict[str, str]
    score_delta: float = Field(default=0, ge=-1000, le=1000)
    correct: bool = False
    feedback_i18n: dict[str, str] = Field(default_factory=dict)

    @field_validator("label_i18n")
    @classmethod
    def validate_label_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)

    @field_validator("feedback_i18n")
    @classmethod
    def validate_feedback_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)


class ScenarioCreateRequest(BaseModel):
    content_version_id: UUID
    scenario_key: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version_number: int = Field(ge=1)
    title_i18n: dict[str, str]
    description_i18n: dict[str, str] = Field(default_factory=dict)
    entry_node_key: str = Field(min_length=1, max_length=120)
    passing_score: float = Field(default=80, ge=0, le=100)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    nodes: list[ScenarioNodeCreate] = Field(min_length=1, max_length=1000)
    edges: list[ScenarioEdgeCreate] = Field(default_factory=list, max_length=5000)
    status: PublicationStatus = "draft"

    @field_validator("title_i18n")
    @classmethod
    def validate_title_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value)

    @field_validator("description_i18n")
    @classmethod
    def validate_description_i18n(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_i18n(value, required=False)

    @model_validator(mode="after")
    def validate_graph(self) -> "ScenarioCreateRequest":
        node_keys = [node.node_key for node in self.nodes]
        known = set(node_keys)
        if len(node_keys) != len(known):
            raise ValueError("Scenario node_key values must be unique")
        if self.entry_node_key not in known:
            raise ValueError("Scenario entry_node_key must reference a declared node")
        edge_keys: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.from_node_key not in known or edge.to_node_key not in known:
                raise ValueError("Scenario edges must reference declared nodes")
            key = (edge.from_node_key, edge.choice_key)
            if key in edge_keys:
                raise ValueError("Scenario choice_key must be unique per source node")
            edge_keys.add(key)
        terminal_keys = {node.node_key for node in self.nodes if node.terminal}
        if not terminal_keys:
            raise ValueError("Scenario requires at least one terminal node")
        return self


class ScenarioStartRequest(BaseModel):
    enrollment_id: UUID


class ScenarioDecisionRequest(BaseModel):
    choice_key: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=1)


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
    playback_session_id: UUID | None = None
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
