from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    warehouse_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=3, max_length=200)
    locations: list[str] = Field(min_length=1)
    products: list[dict] = Field(min_length=1)
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


class TerminalEventCreate(BaseModel):
    # Production terminal identity is authoritative from verified OIDC + managed
    # device headers. Never silently accept tenant/employee/device authority from
    # an offline JSON payload, including stale or malicious queued events.
    model_config = ConfigDict(extra="forbid")

    event_id: str
    document_id: str
    device_sequence: int = Field(gt=0)
    location_id: str = Field(min_length=1, max_length=120)
    barcode: str = Field(min_length=1, max_length=120)
    quantity: float = Field(ge=0, le=1_000_000)
    symbology: str = Field(min_length=1, max_length=80)
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
