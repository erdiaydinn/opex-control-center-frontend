from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


ShipmentMode = Literal["SEVKIYAT", "KARGO"]


class PurchaseOrderResponse(BaseModel):
    po_number: str
    supplier_name: str
    warehouse_name: str
    delivery_date: Optional[str] = None
    status: str
    sku_count: int = 0



class PurchaseOrderImportRow(BaseModel):
    warehouse_name: str
    po_order_id: str = Field(min_length=3)
    supplier_id: Optional[str] = None
    supplier_name: str = Field(min_length=2)
    created_date: Optional[str] = None
    promised_date: Optional[str] = None
    order_status: str = "confirmed"
    total_sku: int = Field(ge=0)


class PurchaseOrderBulkImportRequest(BaseModel):
    rows: List[PurchaseOrderImportRow]
    replace_existing: bool = False


class SlotCapacityResponse(BaseModel):
    warehouse_name: str
    date: str
    slot: str
    max_pallet: int
    max_sku: int
    remaining_pallet: int
    remaining_sku: int


class HoldSlotRequest(BaseModel):
    supplier_name: str
    warehouse_name: str
    slot_date: str
    selected_slot: str
    pallet_count: int = Field(gt=0)
    sku_count: int = Field(gt=0)


class HoldSlotResponse(BaseModel):
    hold_id: str
    status: str
    message: str
    expires_at: str


class CreateReservationRequest(BaseModel):
    po_number: Optional[str] = None
    po_numbers: Optional[List[str]] = None
    supplier_name: str
    warehouse_name: str
    shipment_mode: ShipmentMode

    pallet_count: int = Field(ge=0)
    sku_count: int = Field(default=0, ge=0)

    slot_date: Optional[str] = None
    selected_slot: Optional[str] = None

    shipment_details: Optional[str] = None
    waybill_info: Optional[str] = None
    shipment_form: Optional[str] = None
    box_count: Optional[int] = Field(default=None, ge=0)

    vehicle_type: Optional[str] = None
    vehicle_count: Optional[int] = Field(default=None, ge=0)
    vehicle_plate: Optional[str] = None

    cargo_date: Optional[str] = None
    cargo_tracking_no: Optional[str] = None
    reservation_user: Optional[str] = None


class ReservationResponse(BaseModel):
    reservation_no: str
    status: str
    message: str


class ArrivalCheckRequest(BaseModel):
    arrived: Optional[bool] = None
    dock_compatible: Optional[bool] = None
    on_time: Optional[bool] = None
    ramp_no: Optional[str] = None
    note: Optional[str] = ""


class UpdateSlotCapacityRequest(BaseModel):
    warehouse_name: str
    date: str
    slot: str
    max_pallet: int = Field(ge=0)
    max_sku: int = Field(ge=0)


class BulkCapacityRequest(BaseModel):
    warehouse_name: str
    dates: List[str]
    slots: List[str]
    max_pallet: int = Field(ge=0)
    max_sku: int = Field(ge=0)


class BlockSlotDatesRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    dates: List[str] = Field(min_length=1)


class EditSlotCapacityRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    date: str
    current_slot: str
    new_slot: str
    max_pallet: int = Field(ge=0)
    max_sku: int = Field(ge=0)


class SlotSelectionItem(BaseModel):
    date: str
    slot: str


class BulkSlotEditRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    items: List[SlotSelectionItem] = Field(min_length=1)
    max_pallet: int = Field(ge=0)
    max_sku: int = Field(ge=0)


class BulkSlotDeleteRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    items: List[SlotSelectionItem] = Field(min_length=1)


class SupplierCapacityBulkRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    supplier_name: str = Field(min_length=2)
    dates: List[str]
    slots: List[str]
    reserved_pallet: int = Field(ge=0)
    reserved_sku: int = Field(ge=0)


class SupplierAllocationItem(BaseModel):
    supplier_name: str = Field(min_length=2)
    reserved_pallet: int = Field(ge=0)
    reserved_sku: int = Field(ge=0)
    max_daily_pallet: Optional[int] = Field(default=None, ge=0)


class SupplierCapacityMatrixRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    dates: List[str] = Field(min_length=1)
    slots: List[str] = Field(min_length=1)
    allocations: List[SupplierAllocationItem] = Field(min_length=1)


class AnalyticsAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    filters: Dict[str, Any] = Field(default_factory=dict)


class SupplierDailyLimitRequest(BaseModel):
    warehouse_name: str = Field(min_length=2)
    supplier_name: str = Field(min_length=2)
    dates: List[str] = Field(min_length=1)
    max_pallet: int = Field(ge=0)


class SupplierAccessMappingRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    supplier_names: List[str] = Field(min_length=1)
    warehouse_names: List[str] = Field(default_factory=list)
    all_warehouses: bool = True
    active: bool = True
    locale: Literal["tr", "en", "de", "ar"] = "tr"


class AdminReservationEditRequest(BaseModel):
    slot_date: str
    selected_slot: str
    pallet_count: int = Field(gt=0)
    sku_count: int = Field(gt=0)
    vehicle_plate: str = Field(min_length=3)
    vehicle_type: Optional[str] = None
    shipment_details: str = Field(min_length=5)
    edit_reason: str = Field(min_length=5)


class AdminCommandExecuteRequest(BaseModel):
    action: Literal["SET_DAILY_PALLET_LIMIT"]
    warehouse_name: str = Field(min_length=2)
    supplier_name: str = Field(min_length=2)
    dates: List[str] = Field(min_length=1)
    max_pallet: int = Field(ge=0)


class ReservationStatusRequest(BaseModel):
    status: Literal["APPROVED", "REVISION_REQUESTED", "COMPLETED"]
    note: Optional[str] = ""


class SettingsUpdateRequest(BaseModel):
    supplier_cancel_hours: int = Field(ge=0, le=168)


class ManualPurchaseOrderRequest(BaseModel):
    po_number: str = Field(min_length=3)
    supplier_name: str = Field(min_length=2)
    warehouse_name: str = Field(min_length=2)
    delivery_date: str
    sku_count: int = Field(gt=0)
    pallet_count: int = Field(ge=0)
