import pytest

from app.adapters.frameworks import detect_frameworks


@pytest.mark.parametrize(
    ("marker", "framework", "title", "table_filter"),
    [
        ("django_content_type", "django", "Django", "django_"),
        ("alembic_version", "alembic", "Alembic", "alembic_version"),
        ("databasechangelog", "liquibase", "Liquibase", "databasechangelog"),
        ("wp_options", "wordpress", "WordPress", "wp_"),
    ],
)
def test_a_conventional_marker_supplies_a_titled_literal_filter(
    marker: str, framework: str, title: str, table_filter: str
) -> None:
    expected = [{"id": framework, "title": title, "table_filter": table_filter}]
    assert [item.model_dump() for item in detect_frameworks([marker])] == expected
    assert [
        item.model_dump() for item in detect_frameworks([marker.upper(), marker])
    ] == expected


@pytest.mark.parametrize(
    "names",
    [
        [],
        ["orders", "customers"],
        ["old_django_content_type", "django_contenttype"],
        ["alembic_version_backup"],
        ["databasechangeloglock"],
        ["wp_posts", "custom_options"],
    ],
)
def test_empty_or_similar_names_do_not_claim_a_framework(names: list[str]) -> None:
    assert detect_frameworks(names) == []


def test_every_match_is_returned_once_in_registry_order() -> None:
    names = [
        "wp_options",
        "databasechangelog",
        "alembic_version",
        "django_content_type",
        "alembic_version",
    ]
    assert [item.id for item in detect_frameworks(names)] == [
        "django", "alembic", "liquibase", "wordpress"
    ]
