from pydantic import BaseModel, Field


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
