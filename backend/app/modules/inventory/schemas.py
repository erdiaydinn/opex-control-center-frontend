from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    warehouse_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=3, max_length=200)
    locations: list[str] = Field(min_length=1)
    products: list[dict] = Field(min_length=1)
    count_mode: str = Field(default="GOLDEN_COUNT", pattern="^(GOLDEN_COUNT|WALL_TO_WALL)$")
    thresholds: dict = Field(default_factory=lambda: {"quantity": 5, "value_try": 1000})


class ScanCreate(BaseModel):
    client_event_id: str = Field(min_length=8, max_length=120)
    device_id: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    barcode: str = Field(min_length=1, max_length=120)
    quantity: float = Field(ge=0, le=1_000_000)
    source: str = Field(default="TERMINAL", pattern="^(TERMINAL|OFFLINE_SYNC|MANUAL_PC)$")
    symbology: str = Field(default="UNKNOWN", min_length=1, max_length=80)


class CorrectionCreate(BaseModel):
    line_id: str
    quantity: float = Field(ge=0, le=1_000_000)
    reason: str = Field(min_length=5, max_length=500)


class DecisionCreate(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|REQUEST_RECOUNT)$")
    note: str = Field(min_length=3, max_length=500)


class LocationLockCreate(BaseModel):
    device_id: str = Field(min_length=2, max_length=120)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class TerminalMissionClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    location_id: str = Field(min_length=1, max_length=120)
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")


class TerminalMissionReassignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class TerminalEventCreate(BaseModel):
    # Production terminal identity is authoritative from verified OIDC + managed
    # device headers. Never silently accept tenant/employee/device authority from
    # an offline JSON payload, including stale or malicious queued events.
    # Mission/shift identifiers are server-issued provenance and are all bound
    # into the device-signed canonical payload before historical re-attestation.
    model_config = ConfigDict(extra="forbid")

    event_id: str
    document_id: str
    active_shift_id: str = Field(min_length=1, max_length=128)
    attempt_id: str
    lease_id: str
    device_sequence: int = Field(gt=0)
    location_id: str = Field(min_length=1, max_length=120)
    barcode: str = Field(min_length=1, max_length=120)
    # Preserve weightable-SKU precision through validation/signing instead of
    # round-tripping through binary floating point before PostgreSQL numeric.
    quantity: Decimal = Field(ge=0, le=1_000_000)
    symbology: str = Field(min_length=1, max_length=80)
    occurred_at: str = Field(min_length=20, max_length=50)
    # A second count is never an accidental additive scan. It explicitly links
    # to the evidence version it supersedes; the server validates latest-version
    # authority and preserves both rows.
    recount_of_event_id: str | None = None
    recount_reason_code: str | None = Field(default=None, min_length=1, max_length=40)
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")


class LocationCompletionCreate(BaseModel):
    # Location completion is a distinct signed terminal event. It carries no
    # barcode, SKU, expected stock or stock quantity truth. confirmed_line_count
    # is only the number of blind-count evidence events in this mission attempt;
    # the server independently counts committed rows for the same attempt.
    model_config = ConfigDict(extra="forbid")

    event_id: str
    document_id: str
    active_shift_id: str = Field(min_length=1, max_length=128)
    attempt_id: str
    lease_id: str
    event_kind: str = Field(default="LOCATION_COMPLETE", pattern="^LOCATION_COMPLETE$")
    confirmed_line_count: int = Field(ge=0, le=1_000_000)
    device_sequence: int = Field(gt=0)
    location_id: str = Field(min_length=1, max_length=120)
    occurred_at: str = Field(min_length=20, max_length=50)
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")


class DocumentTransitionCreate(BaseModel):
    expected_revision: int = Field(gt=0)
    target_state: str = Field(pattern="^(SUBMITTED|RECONCILING|APPROVED|LOCKED|REJECTED)$")
    reason: str = Field(min_length=3, max_length=500)


class DeviceEnrollCreate(BaseModel):
    # Tenant and employee bindings come only from the authenticated principal.
    model_config = ConfigDict(extra="forbid")

    activation_code: str = Field(min_length=32, max_length=256)
    public_key_pem: str = Field(min_length=100, max_length=2000)


class DeviceReplaceCreate(BaseModel):
    """Managed replacement request issued from the new physical device.

    Tenant, employee and new-device identity never come from this body. They are
    derived from verified OIDC plus X-EAY-Device-ID. The old device id is only the
    authority being revoked/superseded; queued evidence is never rebound to the
    replacement device.
    """

    model_config = ConfigDict(extra="forbid")

    replaced_device_id: str = Field(min_length=36, max_length=36)
    activation_code: str = Field(min_length=32, max_length=256)
    public_key_pem: str = Field(min_length=100, max_length=2000)


class RecoveryCaseCreate(BaseModel):
    """Request supervisor review of one operationally recoverable quarantine.

    Policy/identity/device/contract-integrity failures are deliberately excluded
    from this business recovery path. Raw barcode/quantity payload is not accepted;
    only immutable event identity/hash and safe provenance may enter review.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=36, max_length=36)
    document_id: str = Field(min_length=36, max_length=36)
    location_id: str = Field(min_length=1, max_length=120)
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")
    quarantine_reason: str = Field(
        pattern="^(BUSINESS_CONFLICT|DEPENDENCY_BLOCKED|RETRY_EXHAUSTED)$"
    )
    server_code: str | None = Field(default=None, max_length=120)


class RecoveryDispositionCreate(BaseModel):
    """Maker-checker disposition for one recovery case.

    SERVER_EVIDENCE_CONFIRMED is accepted only when the backend independently
    finds the exact event id + payload hash in authoritative Inventory events.
    Other decisions never mutate or rebind the quarantined local event.
    """

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(
        pattern="^(RECOUNT_REQUIRED|SERVER_EVIDENCE_CONFIRMED|LOCAL_EVIDENCE_INVALID|SECURITY_ESCALATED)$"
    )
    reason: str = Field(min_length=3, max_length=500)


class OperationalMissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: str = Field(min_length=1, max_length=120)
    mission_type: str = Field(pattern="^(PICKING|PUTAWAY|RECEIVING|TRANSFER)$")
    external_reference: str = Field(min_length=1, max_length=160)
    sku_id: str = Field(min_length=1, max_length=160)
    # This value crosses only the authenticated backend boundary. It is hashed
    # immediately and is never stored or returned as mission presentation truth.
    item_barcode: str = Field(min_length=1, max_length=160)
    planned_quantity: Decimal = Field(gt=0, le=1_000_000)
    source_location_id: str | None = Field(default=None, min_length=1, max_length=120)
    destination_location_id: str | None = Field(default=None, min_length=1, max_length=120)
    container_id: str | None = Field(default=None, min_length=1, max_length=160)
    allowed_conditions: list[str] = Field(
        default_factory=lambda: ["GOOD", "DAMAGED", "EXPIRED", "NO_BARCODE"],
        min_length=1,
        max_length=16,
    )
    # Service metadata is server-owned scheduling truth. It is never accepted
    # from the field terminal and never grants execution authority by itself.
    priority: str = Field(default="NORMAL", pattern="^(LOW|NORMAL|HIGH|URGENT)$")
    due_at: str | None = Field(default=None, min_length=20, max_length=50)
    estimated_seconds: int | None = Field(default=None, ge=1, le=86_400)


class OperationalEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    mission_id: str
    claim_id: str
    active_shift_id: str = Field(min_length=1, max_length=128)
    device_sequence: int = Field(gt=0)
    step_kind: str = Field(
        pattern="^(SOURCE_LOCATION|DESTINATION_LOCATION|ITEM|QUANTITY|CONDITION|CONTAINER|COMPLETE)$"
    )
    # The raw step value is accepted only to verify the signed value hash and
    # frozen mission intent. ITEM is never persisted or returned in raw form.
    value: str = Field(min_length=1, max_length=200)
    value_hash: str = Field(pattern="^[0-9a-f]{64}$")
    occurred_at: str = Field(min_length=20, max_length=50)
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")