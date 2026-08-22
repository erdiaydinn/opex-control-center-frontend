"""Extended executive-context taxonomy for EAY Jarvis.

The base correlation engine intentionally stays small and stable. This module
maps richer real-world context categories into those governed primitives so new
providers can be added without fragmenting causal, source or tenant boundaries.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .context_intelligence import ContextKind, ImpactDimension

CONTEXT_TAXONOMY_CONTRACT = "eay-context-taxonomy-v1"


class ExecutiveContextCategory(str, Enum):
    PUBLIC_HOLIDAY = "public_holiday"
    RELIGIOUS_SEASON = "religious_season"
    SCHOOL_CALENDAR = "school_calendar"
    PAYDAY_CYCLE = "payday_cycle"
    SPORTS_EVENT = "sports_event"
    CONCERT_FESTIVAL = "concert_festival"
    TOURISM_TRAVEL_FLOW = "tourism_travel_flow"
    PORT_AIRPORT_DISRUPTION = "port_airport_disruption"
    INFRASTRUCTURE_OUTAGE = "infrastructure_outage"
    ENERGY_UTILITY = "energy_utility"
    DIGITAL_SERVICE_OUTAGE = "digital_service_outage"
    SUPPLY_CHAIN_DISRUPTION = "supply_chain_disruption"
    COMPETITOR_MARKET_MOVE = "competitor_market_move"
    PUBLIC_SAFETY_EMERGENCY = "public_safety_emergency"
    PUBLIC_HEALTH_SIGNAL = "public_health_signal"
    SOCIAL_SENTIMENT = "social_sentiment"


class ContextCategorySpec(BaseModel):
    contract: str = CONTEXT_TAXONOMY_CONTRACT
    category: ExecutiveContextCategory
    base_kind: ContextKind
    expected_impacts: tuple[ImpactDimension, ...] = Field(min_length=1)
    official_source_required: bool = False
    min_independent_sources: int = Field(default=1, ge=1, le=5)
    lead_time_relevant: bool = True


CATEGORY_SPECS: dict[ExecutiveContextCategory, ContextCategorySpec] = {
    ExecutiveContextCategory.PUBLIC_HOLIDAY: ContextCategorySpec(
        category=ExecutiveContextCategory.PUBLIC_HOLIDAY,
        base_kind=ContextKind.CITY_EVENT,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.ORDER_VOLUME, ImpactDimension.LABOR),
        official_source_required=True,
    ),
    ExecutiveContextCategory.RELIGIOUS_SEASON: ContextCategorySpec(
        category=ExecutiveContextCategory.RELIGIOUS_SEASON,
        base_kind=ContextKind.CITY_EVENT,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.ORDER_VOLUME, ImpactDimension.LABOR),
        official_source_required=True,
    ),
    ExecutiveContextCategory.SCHOOL_CALENDAR: ContextCategorySpec(
        category=ExecutiveContextCategory.SCHOOL_CALENDAR,
        base_kind=ContextKind.CITY_EVENT,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.DELIVERY_SPEED, ImpactDimension.LABOR),
        official_source_required=True,
    ),
    ExecutiveContextCategory.PAYDAY_CYCLE: ContextCategorySpec(
        category=ExecutiveContextCategory.PAYDAY_CYCLE,
        base_kind=ContextKind.MACRO_ECONOMIC,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.REVENUE),
    ),
    ExecutiveContextCategory.SPORTS_EVENT: ContextCategorySpec(
        category=ExecutiveContextCategory.SPORTS_EVENT,
        base_kind=ContextKind.CITY_EVENT,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.ORDER_VOLUME, ImpactDimension.DELIVERY_SPEED),
    ),
    ExecutiveContextCategory.CONCERT_FESTIVAL: ContextCategorySpec(
        category=ExecutiveContextCategory.CONCERT_FESTIVAL,
        base_kind=ContextKind.CITY_EVENT,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.STORE_ACCESS, ImpactDimension.DELIVERY_SPEED),
    ),
    ExecutiveContextCategory.TOURISM_TRAVEL_FLOW: ContextCategorySpec(
        category=ExecutiveContextCategory.TOURISM_TRAVEL_FLOW,
        base_kind=ContextKind.MACRO_ECONOMIC,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.REVENUE, ImpactDimension.LABOR),
        min_independent_sources=2,
    ),
    ExecutiveContextCategory.PORT_AIRPORT_DISRUPTION: ContextCategorySpec(
        category=ExecutiveContextCategory.PORT_AIRPORT_DISRUPTION,
        base_kind=ContextKind.TRANSIT_DISRUPTION,
        expected_impacts=(ImpactDimension.AVAILABILITY, ImpactDimension.COST, ImpactDimension.DELIVERY_SPEED),
        official_source_required=True,
    ),
    ExecutiveContextCategory.INFRASTRUCTURE_OUTAGE: ContextCategorySpec(
        category=ExecutiveContextCategory.INFRASTRUCTURE_OUTAGE,
        base_kind=ContextKind.LOCAL_INCIDENT,
        expected_impacts=(ImpactDimension.STORE_ACCESS, ImpactDimension.AVAILABILITY, ImpactDimension.CLOSURE_TIME),
        official_source_required=True,
    ),
    ExecutiveContextCategory.ENERGY_UTILITY: ContextCategorySpec(
        category=ExecutiveContextCategory.ENERGY_UTILITY,
        base_kind=ContextKind.LOCAL_INCIDENT,
        expected_impacts=(ImpactDimension.COST, ImpactDimension.AVAILABILITY, ImpactDimension.CLOSURE_TIME),
        official_source_required=True,
    ),
    ExecutiveContextCategory.DIGITAL_SERVICE_OUTAGE: ContextCategorySpec(
        category=ExecutiveContextCategory.DIGITAL_SERVICE_OUTAGE,
        base_kind=ContextKind.LOCAL_INCIDENT,
        expected_impacts=(ImpactDimension.ORDER_VOLUME, ImpactDimension.CUSTOMER_EXPERIENCE, ImpactDimension.REVENUE),
        min_independent_sources=2,
    ),
    ExecutiveContextCategory.SUPPLY_CHAIN_DISRUPTION: ContextCategorySpec(
        category=ExecutiveContextCategory.SUPPLY_CHAIN_DISRUPTION,
        base_kind=ContextKind.NEWS_AGENDA,
        expected_impacts=(ImpactDimension.AVAILABILITY, ImpactDimension.COST, ImpactDimension.MARGIN),
        min_independent_sources=2,
    ),
    ExecutiveContextCategory.COMPETITOR_MARKET_MOVE: ContextCategorySpec(
        category=ExecutiveContextCategory.COMPETITOR_MARKET_MOVE,
        base_kind=ContextKind.NEWS_AGENDA,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.REVENUE, ImpactDimension.MARGIN),
        min_independent_sources=2,
    ),
    ExecutiveContextCategory.PUBLIC_SAFETY_EMERGENCY: ContextCategorySpec(
        category=ExecutiveContextCategory.PUBLIC_SAFETY_EMERGENCY,
        base_kind=ContextKind.LOCAL_INCIDENT,
        expected_impacts=(ImpactDimension.STORE_ACCESS, ImpactDimension.LABOR, ImpactDimension.DELIVERY_SPEED),
        official_source_required=True,
    ),
    ExecutiveContextCategory.PUBLIC_HEALTH_SIGNAL: ContextCategorySpec(
        category=ExecutiveContextCategory.PUBLIC_HEALTH_SIGNAL,
        base_kind=ContextKind.NEWS_AGENDA,
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.LABOR, ImpactDimension.COMPLIANCE),
        official_source_required=True,
    ),
    ExecutiveContextCategory.SOCIAL_SENTIMENT: ContextCategorySpec(
        category=ExecutiveContextCategory.SOCIAL_SENTIMENT,
        base_kind=ContextKind.NEWS_AGENDA,
        expected_impacts=(ImpactDimension.CUSTOMER_EXPERIENCE, ImpactDimension.DEMAND, ImpactDimension.REVENUE),
        min_independent_sources=2,
        lead_time_relevant=False,
    ),
}


def require_context_category(category: ExecutiveContextCategory | str) -> ContextCategorySpec:
    key = ExecutiveContextCategory(category)
    return CATEGORY_SPECS[key]
