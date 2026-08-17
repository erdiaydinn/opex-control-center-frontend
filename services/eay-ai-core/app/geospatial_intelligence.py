"""Geospatial context primitives for EAY Jarvis.

External events rarely affect an entire city uniformly. This module provides a
deterministic hierarchy/radius overlap check so city events, weather cells,
road closures and incidents can be related to specific districts or stores
without relying on brittle free-text equality.
"""

from __future__ import annotations

import unicodedata
from math import asin, cos, isfinite, radians, sin, sqrt

from pydantic import BaseModel, Field, model_validator

GEOSPATIAL_INTELLIGENCE_CONTRACT = "eay-geospatial-intelligence-v1"
EARTH_RADIUS_KM = 6371.0088


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    folded = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.split())


class GeoScope(BaseModel):
    scope_id: str = Field(min_length=1, max_length=180)
    country: str = Field(min_length=1, max_length=120)
    city: str | None = Field(default=None, max_length=180)
    district: str | None = Field(default=None, max_length=180)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    radius_km: float | None = Field(default=None, ge=0.0, le=1000.0)

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "GeoScope":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("geo_scope_coordinate_pair_required")
        if self.radius_km is not None and self.latitude is None:
            raise ValueError("geo_scope_radius_requires_coordinates")
        for field in ("latitude", "longitude", "radius_km"):
            value = getattr(self, field)
            if value is not None and not isfinite(float(value)):
                raise ValueError(f"geo_scope_{field}_must_be_finite")
        return self


class GeoOverlap(BaseModel):
    contract: str = GEOSPATIAL_INTELLIGENCE_CONTRACT
    left_scope_id: str
    right_scope_id: str
    score: float = Field(ge=0.0, le=1.0)
    distance_km: float | None = None
    hierarchy_match: str
    within_radius: bool = False


def haversine_km(left: GeoScope, right: GeoScope) -> float | None:
    if left.latitude is None or right.latitude is None:
        return None
    lat1 = radians(left.latitude)
    lon1 = radians(left.longitude)
    lat2 = radians(right.latitude)
    lon2 = radians(right.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * asin(sqrt(value)), 6)


def evaluate_geo_overlap(left: GeoScope, right: GeoScope) -> GeoOverlap:
    if _norm(left.country) != _norm(right.country):
        return GeoOverlap(
            left_scope_id=left.scope_id,
            right_scope_id=right.scope_id,
            score=0.0,
            hierarchy_match="country_mismatch",
        )

    hierarchy_score = 0.25
    hierarchy_match = "country"
    if left.city and right.city and _norm(left.city) == _norm(right.city):
        hierarchy_score = 0.70
        hierarchy_match = "city"
        if left.district and right.district and _norm(left.district) == _norm(right.district):
            hierarchy_score = 1.0
            hierarchy_match = "district"
    elif left.city and right.city:
        hierarchy_score = 0.0
        hierarchy_match = "city_mismatch"

    distance = haversine_km(left, right)
    within_radius = False
    radial_score = 0.0
    if distance is not None:
        combined_radius = (left.radius_km or 0.0) + (right.radius_km or 0.0)
        if combined_radius > 0 and distance <= combined_radius:
            within_radius = True
            radial_score = max(0.0, 1.0 - (distance / max(combined_radius, 0.001)))
        elif distance <= 2.0:
            radial_score = 0.85
        elif distance <= 5.0:
            radial_score = 0.65
        elif distance <= 15.0:
            radial_score = 0.40

    score = max(hierarchy_score, radial_score)
    return GeoOverlap(
        left_scope_id=left.scope_id,
        right_scope_id=right.scope_id,
        score=round(min(max(score, 0.0), 1.0), 6),
        distance_km=distance,
        hierarchy_match=hierarchy_match,
        within_radius=within_radius,
    )
