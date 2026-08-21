from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (
        REPO_ROOT / path
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def _location_block(
    text: str,
    marker: str,
) -> str:
    start = text.index(marker)

    open_brace = text.index(
        "{",
        start,
    )

    close_brace = text.index(
        "}",
        open_brace,
    )

    return text[
        start:close_brace + 1
    ]


def _assert_quarantined(text: str) -> None:
    exact = "location = /api/dockos"
    subtree = "location ^~ /api/dockos/"
    generic = "location /api/"

    assert exact in text
    assert subtree in text
    assert generic in text

    # Both quarantine rules must be evaluated before
    # the generic API proxy.
    assert text.index(exact) < text.index(generic)
    assert text.index(subtree) < text.index(generic)

    for marker in (
        exact,
        subtree,
    ):
        block = _location_block(
            text,
            marker,
        )

        # Each DockOS location independently terminates
        # at the edge and never reaches Core API.
        assert block.count(
            "return 404;"
        ) == 1

        assert "proxy_pass" not in block
        assert "core-api:8000" not in block
        assert "return 200" not in block
        assert "return 30" not in block

def test_development_gateway_quarantines_dockos() -> None:
    _assert_quarantined(
        _read("infra/nginx/platform.conf")
    )


def test_production_gateway_quarantines_dockos() -> None:
    _assert_quarantined(
        _read(
            "infra/nginx/"
            "platform.production.conf.template"
        )
    )


def test_dockos_quarantine_is_fail_closed() -> None:
    for path in (
        "infra/nginx/platform.conf",
        "infra/nginx/"
        "platform.production.conf.template",
    ):
        text = _read(path)

        assert (
            "location = /api/dockos {"
            in text
        )
        assert (
            "location ^~ /api/dockos/ {"
            in text
        )

        # No accidental redirect or auth bypass.
        start = text.index(
            "location = /api/dockos"
        )
        end = text.index(
            "location /api/",
            start,
        )

        block = text[start:end]

        assert "return 200" not in block
        assert "return 30" not in block
        assert "proxy_pass" not in block
