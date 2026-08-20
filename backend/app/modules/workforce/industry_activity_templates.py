"""Starter work-activity templates for multi-industry Workforce deployments.

Templates are convenience candidates only. They do not contain labor timings,
do not become scheduling authority by being present, and must be cloned into a
tenant's governed activity catalog and paired with approved labor standards.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActivityTemplateItem:
    activity_key: str
    display_name: str
    category: str
    unit_key: str
    demand_mode: str = "VOLUME"
    required_skill_keys: tuple[str, ...] = ()
    required_certification_keys: tuple[str, ...] = ()
    required_equipment_keys: tuple[str, ...] = ()
    safety_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IndustryActivityTemplate:
    template_key: str
    display_name: str
    location_type: str
    activities: tuple[ActivityTemplateItem, ...]


DARKSTORE = IndustryActivityTemplate(
    template_key="darkstore",
    display_name="E-grocery / darkstore",
    location_type="darkstore",
    activities=(
        ActivityTemplateItem("order_picking", "Order picking", "fulfillment", "items", required_skill_keys=("order_picking",)),
        ActivityTemplateItem("order_packing", "Order packing", "fulfillment", "orders", required_skill_keys=("order_packing",)),
        ActivityTemplateItem("order_handoff", "Order handoff", "fulfillment", "orders"),
        ActivityTemplateItem("po_receiving", "Purchase-order receiving", "inbound", "items", required_skill_keys=("receiving",)),
        ActivityTemplateItem("transfer_receiving", "Transfer receiving", "inbound", "items", required_skill_keys=("receiving",)),
        ActivityTemplateItem("putaway", "Putaway", "inbound", "items", required_skill_keys=("putaway",)),
        ActivityTemplateItem("cycle_count", "Cycle count", "inventory", "items", required_skill_keys=("inventory_count",)),
        ActivityTemplateItem("expiry_check", "Expiry check", "quality", "items"),
        ActivityTemplateItem("quality_check", "Quality check", "quality", "items"),
        ActivityTemplateItem("replenishment", "Replenishment", "inventory", "items"),
        ActivityTemplateItem("outbound_transfer", "Outbound transfer", "outbound", "items"),
        ActivityTemplateItem("returned_order_putaway", "Returned-order putaway", "returns", "items"),
    ),
)

QSR = IndustryActivityTemplate(
    template_key="qsr",
    display_name="Quick-service restaurant",
    location_type="restaurant",
    activities=(
        ActivityTemplateItem("food_grill_cook", "Grill cooking", "food_production", "items", required_skill_keys=("grill_station",), required_certification_keys=("food_safety",), safety_tags=("hot_surface", "food_safety")),
        ActivityTemplateItem("food_fryer_cook", "Fryer cooking", "food_production", "items", required_skill_keys=("fryer_station",), required_certification_keys=("food_safety",), safety_tags=("hot_oil", "food_safety")),
        ActivityTemplateItem("order_assembly", "Order assembly", "fulfillment", "orders", required_skill_keys=("order_assembly",), required_certification_keys=("food_safety",)),
        ActivityTemplateItem("beverage_prepare", "Beverage preparation", "food_production", "drinks", required_certification_keys=("food_safety",)),
        ActivityTemplateItem("counter_service", "Counter service", "service", "transactions", required_skill_keys=("customer_service",)),
        ActivityTemplateItem("drive_thru_handoff", "Drive-through handoff", "service", "orders", required_skill_keys=("customer_service",)),
        ActivityTemplateItem("warmer_sanitation", "Warmer sanitation", "sanitation", "cycles", demand_mode="FIXED", required_certification_keys=("food_safety",), safety_tags=("food_safety", "sanitation")),
        ActivityTemplateItem("opening_sanitation", "Opening sanitation", "sanitation", "cycles", demand_mode="FIXED", required_certification_keys=("food_safety",), safety_tags=("sanitation",)),
        ActivityTemplateItem("closing_sanitation", "Closing sanitation", "sanitation", "cycles", demand_mode="FIXED", required_certification_keys=("food_safety",), safety_tags=("sanitation",)),
        ActivityTemplateItem("goods_receiving", "Goods receiving", "inbound", "items", required_skill_keys=("receiving",)),
        ActivityTemplateItem("inventory_count", "Inventory count", "inventory", "items", required_skill_keys=("inventory_count",)),
    ),
)

SUPERMARKET = IndustryActivityTemplate(
    template_key="supermarket",
    display_name="Supermarket / retail",
    location_type="store",
    activities=(
        ActivityTemplateItem("shelf_replenishment", "Shelf replenishment", "merchandising", "items", required_skill_keys=("replenishment",)),
        ActivityTemplateItem("checkout_service", "Checkout service", "service", "transactions", required_skill_keys=("checkout",)),
        ActivityTemplateItem("deli_service", "Deli service", "service", "orders", required_certification_keys=("food_safety",)),
        ActivityTemplateItem("bakery_prepare", "Bakery preparation", "food_production", "batches", required_skill_keys=("bakery",), required_certification_keys=("food_safety",)),
        ActivityTemplateItem("produce_quality_check", "Produce quality check", "quality", "items"),
        ActivityTemplateItem("expiry_check", "Expiry check", "quality", "items"),
        ActivityTemplateItem("goods_receiving", "Goods receiving", "inbound", "items", required_skill_keys=("receiving",)),
        ActivityTemplateItem("inventory_count", "Inventory count", "inventory", "items", required_skill_keys=("inventory_count",)),
        ActivityTemplateItem("store_sanitation", "Store sanitation", "sanitation", "cycles", demand_mode="FIXED", safety_tags=("sanitation",)),
    ),
)

MANUFACTURING = IndustryActivityTemplate(
    template_key="manufacturing",
    display_name="Manufacturing / factory",
    location_type="factory",
    activities=(
        ActivityTemplateItem("machine_operation", "Machine operation", "production", "units", required_skill_keys=("machine_operation",), required_certification_keys=("machine_authorization",), safety_tags=("machine_safety",)),
        ActivityTemplateItem("line_changeover", "Line setup / changeover", "production", "cycles", demand_mode="FIXED", required_skill_keys=("line_changeover",), safety_tags=("machine_safety",)),
        ActivityTemplateItem("assembly", "Assembly", "production", "units", required_skill_keys=("assembly",)),
        ActivityTemplateItem("production_packing", "Production packing", "outbound", "units", required_skill_keys=("packing",)),
        ActivityTemplateItem("quality_control", "Quality control", "quality", "units", required_skill_keys=("quality_control",)),
        ActivityTemplateItem("material_handling", "Material handling", "material_flow", "pallets", required_skill_keys=("material_handling",), required_equipment_keys=("material_handling_equipment",)),
        ActivityTemplateItem("line_sanitation", "Line sanitation", "sanitation", "cycles", demand_mode="FIXED", safety_tags=("sanitation", "machine_safety")),
        ActivityTemplateItem("maintenance_assist", "Maintenance assistance", "maintenance", "events", demand_mode="EVENT", required_skill_keys=("maintenance_assist",), safety_tags=("machine_safety",)),
    ),
)

CONVENIENCE_KIOSK = IndustryActivityTemplate(
    template_key="convenience_kiosk",
    display_name="Convenience store / kiosk",
    location_type="kiosk",
    activities=(
        ActivityTemplateItem("checkout_service", "Checkout service", "service", "transactions", required_skill_keys=("checkout",)),
        ActivityTemplateItem("food_prepare", "Food preparation", "food_production", "items", required_certification_keys=("food_safety",)),
        ActivityTemplateItem("beverage_prepare", "Beverage preparation", "food_production", "drinks", required_certification_keys=("food_safety",)),
        ActivityTemplateItem("restocking", "Restocking", "inventory", "items"),
        ActivityTemplateItem("kiosk_cleaning", "Cleaning", "sanitation", "cycles", demand_mode="FIXED", safety_tags=("sanitation",)),
        ActivityTemplateItem("goods_receiving", "Goods receiving", "inbound", "items", required_skill_keys=("receiving",)),
        ActivityTemplateItem("closing_control", "Closing control", "operations", "cycles", demand_mode="FIXED"),
    ),
)


TEMPLATES = {
    template.template_key: template
    for template in (DARKSTORE, QSR, SUPERMARKET, MANUFACTURING, CONVENIENCE_KIOSK)
}

# Compatibility only: existing darkstore demand keys can migrate into the new
# generic ontology without changing the original formulas in-place.
LEGACY_DARKSTORE_ACTIVITY_MAP = {
    "picking": "order_picking",
    "packing": "order_packing",
    "handoff": "order_handoff",
    "receiving_po": "po_receiving",
    "receiving_st": "transfer_receiving",
    "putaway": "putaway",
    "cycle_count": "cycle_count",
    "expiry_check": "expiry_check",
    "quality_check": "quality_check",
    "replenishment": "replenishment",
    "outbound_transfer": "outbound_transfer",
    "returned_order_putaway": "returned_order_putaway",
}


def list_templates() -> tuple[IndustryActivityTemplate, ...]:
    return tuple(TEMPLATES[key] for key in sorted(TEMPLATES))


def get_template(template_key: str) -> IndustryActivityTemplate:
    try:
        return TEMPLATES[str(template_key).strip()]
    except KeyError as error:
        raise KeyError(f"unknown Workforce activity template: {template_key}") from error


def starter_candidates(template_key: str) -> tuple[dict[str, object], ...]:
    """Return non-authoritative candidate activity definitions.

    No seconds-per-unit, staffing ratio or approval field is emitted here. A
    tenant must explicitly approve activity versions and labor standards later.
    """
    template = get_template(template_key)
    return tuple(
        {
            "activity_key": item.activity_key,
            "display_name": item.display_name,
            "category": item.category,
            "unit_key": item.unit_key,
            "demand_mode": item.demand_mode,
            "required_skill_keys": list(item.required_skill_keys),
            "required_certification_keys": list(item.required_certification_keys),
            "required_equipment_keys": list(item.required_equipment_keys),
            "safety_tags": list(item.safety_tags),
            "location_types": [template.location_type],
            "template_key": template.template_key,
        }
        for item in template.activities
    )
