from app.geospatial_intelligence import GeoScope, evaluate_geo_overlap, haversine_km


def test_same_district_is_full_hierarchy_match():
    event = GeoScope(scope_id="event", country="TR", city="Istanbul", district="Kadikoy")
    store = GeoScope(scope_id="store", country="TR", city="İstanbul", district="Kadıköy")

    overlap = evaluate_geo_overlap(event, store)

    assert overlap.score == 1.0
    assert overlap.hierarchy_match == "district"


def test_same_city_different_district_still_has_city_context():
    event = GeoScope(scope_id="event", country="TR", city="Istanbul", district="Besiktas")
    store = GeoScope(scope_id="store", country="TR", city="Istanbul", district="Kadikoy")

    overlap = evaluate_geo_overlap(event, store)

    assert overlap.score >= 0.70
    assert overlap.hierarchy_match == "city"


def test_radius_can_identify_nearby_store_impact_beyond_text_labels():
    road_closure = GeoScope(
        scope_id="closure",
        country="TR",
        city="Istanbul",
        district="Fatih",
        latitude=41.015,
        longitude=28.979,
        radius_km=4.0,
    )
    store = GeoScope(
        scope_id="store",
        country="TR",
        city="Istanbul",
        district="Beyoglu",
        latitude=41.028,
        longitude=28.974,
        radius_km=1.0,
    )

    overlap = evaluate_geo_overlap(road_closure, store)

    assert overlap.distance_km is not None
    assert overlap.distance_km < 5.0
    assert overlap.within_radius is True
    assert overlap.score >= 0.69


def test_different_city_does_not_inherit_country_only_match_when_city_is_known():
    istanbul = GeoScope(scope_id="istanbul", country="TR", city="Istanbul")
    ankara = GeoScope(scope_id="ankara", country="TR", city="Ankara")

    overlap = evaluate_geo_overlap(istanbul, ankara)

    assert overlap.score == 0.0
    assert overlap.hierarchy_match == "city_mismatch"


def test_haversine_returns_none_without_coordinates():
    assert haversine_km(
        GeoScope(scope_id="a", country="TR", city="Istanbul"),
        GeoScope(scope_id="b", country="TR", city="Istanbul"),
    ) is None
