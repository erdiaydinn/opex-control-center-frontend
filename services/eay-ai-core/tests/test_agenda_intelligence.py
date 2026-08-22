from datetime import datetime, timedelta, timezone

from app.agenda_intelligence import AgendaItem, AgendaStatus, build_agenda_digest

UTC = timezone.utc
BASE = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _item(
    item_id: str,
    domain: str,
    title: str,
    *,
    minutes: int = 0,
    official: bool = False,
    location: str = "Istanbul",
    topic: str = "transport",
    confidence: float = 0.9,
) -> AgendaItem:
    published = BASE + timedelta(minutes=minutes)
    return AgendaItem(
        item_id=item_id,
        title=title,
        summary="Major road closures are expected around the event route.",
        published_at=published,
        fetched_at=published + timedelta(minutes=5),
        source_name=domain,
        source_url=f"https://{domain}/news/{item_id}",
        source_confidence=confidence,
        locations=(location,),
        topics=(topic,),
        official=official,
    )


def test_same_event_from_two_independent_sources_is_corroborated():
    digest = build_agenda_digest(
        [
            _item("a", "city.example", "Istanbul marathon road closures", official=True),
            _item("b", "news.example", "Road closures for Istanbul marathon", minutes=10),
        ]
    )

    assert len(digest.clusters) == 1
    cluster = digest.clusters[0]
    assert cluster.status in {AgendaStatus.CORROBORATED, AgendaStatus.HIGH_CONFIDENCE}
    assert cluster.independent_source_count == 2
    assert cluster.official_source_present is True


def test_same_domain_syndication_does_not_count_as_independent_corroboration():
    digest = build_agenda_digest(
        [
            _item("a", "news.example", "Istanbul marathon road closures"),
            _item("b", "news.example", "Istanbul marathon road closures announced", minutes=2),
        ]
    )

    assert len(digest.clusters) == 1
    assert digest.clusters[0].independent_source_count == 1
    assert digest.clusters[0].status is AgendaStatus.UNCORROBORATED
    assert "b" in digest.duplicate_item_ids


def test_different_locations_do_not_merge_even_with_similar_headlines():
    digest = build_agenda_digest(
        [
            _item("istanbul", "news-a.example", "Marathon road closures", location="Istanbul"),
            _item("ankara", "news-b.example", "Marathon road closures", location="Ankara"),
        ]
    )

    assert len(digest.clusters) == 2


def test_old_article_does_not_merge_with_new_event_cycle():
    old = _item("old", "news-a.example", "Istanbul marathon road closures")
    new = _item("new", "news-b.example", "Istanbul marathon road closures", minutes=19 * 60)

    digest = build_agenda_digest([old, new])

    assert len(digest.clusters) == 2


def test_agenda_item_cannot_promote_itself_out_of_context_boundary():
    payload = _item("a", "news.example", "Istanbul marathon road closures").model_dump()
    payload["context_only"] = False

    try:
        AgendaItem.model_validate(payload)
    except ValueError as exc:
        assert "agenda_item_must_remain_context_only" in str(exc)
    else:
        raise AssertionError("context boundary should reject non-context agenda item")
