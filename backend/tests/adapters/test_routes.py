from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/adapter-types"


async def test_lists_postgres_with_json_schema(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert response.status_code == 200
    types = {item["name"]: item for item in response.json()}
    assert types["postgres"]["title"] == "PostgreSQL"
    schema = types["postgres"]["options_schema"]
    # A type whose fields depend on the way it is connected to answers with a
    # union: the variants in $defs, the choice in the discriminator.
    assert schema["discriminator"]["propertyName"] == "auth_method"
    assert set(schema["discriminator"]["mapping"]) == {"user_password", "no_auth"}
    properties = schema["$defs"]["PostgresUserPassword"]["properties"]
    assert properties["host"]["title"] == "Host"
    # Defaults the form starts from: the commonest address there is, rather
    # than two empty boxes.
    assert properties["host"]["default"] == "localhost"
    assert properties["port"]["default"] == 5432


async def test_a_variant_is_named_by_the_title_it_declares(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The wording of the pick list, so it is the server that supplies it."""
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    types = {item["name"]: item for item in response.json()}
    defs = types["postgres"]["options_schema"]["$defs"]

    assert defs["PostgresUserPassword"]["title"] == "User & Password"
    assert defs["PostgresNoAuth"]["title"] == "No auth"


async def test_a_type_with_one_way_of_connecting_stays_a_plain_schema(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Nothing forces a union on a source that has no choice to offer."""
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    types = {item["name"]: item for item in response.json()}
    schema = types["file"]["options_schema"]

    assert "oneOf" not in schema
    assert schema["properties"]["path"]["title"] == "Path"


async def test_secret_fields_are_marked_as_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    postgres = next(item for item in response.json() if item["name"] == "postgres")
    variant = postgres["options_schema"]["$defs"]["PostgresUserPassword"]
    assert variant["properties"]["password"]["format"] == "password"


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/")

    assert response.status_code == 401


async def test_reports_the_category_and_description_of_a_type(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    types = {item["name"]: item for item in response.json()}
    assert types["postgres"]["category"] == "sql"
    assert types["postgres"]["category_title"] == "SQL Databases"
    assert types["postgres"]["description"] != ""
    assert types["file"]["category"] == "files"


async def test_reports_what_a_type_can_do(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Derived from the driver, so the answer cannot outlive the capability."""
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    types = {item["name"]: item for item in response.json()}
    postgres = [c["title"] for c in types["postgres"]["capabilities"]]
    files = [c["title"] for c in types["file"]["capabilities"]]

    assert "Browse the catalog" in postgres
    assert "Read rows" in postgres
    assert "View content" in postgres
    assert "View content" in files
    assert "Download" in files
    assert "Download" in {
        c["title"]
        for c in types["file"]["capabilities"]
        if c["group"] == "explore"
    }
    assert "Describe a relation" in postgres
    # A file source describes the two formats that state their own columns
    # (D51); what it still cannot do is answer for the rest, which is a node
    # question rather than a type one.
    assert "Describe a relation" in files
    assert "Follow references" in postgres
    assert "Follow references" not in files
    assert {c["title"] for c in types["postgres"]["capabilities"] if c["group"] == "manage"} == {
        "Edit rows",
        "Insert rows",
        "Delete rows",
        "Add columns",
        "Drop columns",
        "Rename",
        "Load from CSV",
        "Create table",
        "Drop",
        "New schema",
        "Rename schema",
        "Move to schema",
        "Drop schema",
        "New role",
        "New tablespace",
        "Rename tablespace",
        "Change tablespace owner",
        # Installing and removing an extension are row commands of the report
        # that lists them rather than actions of the type: they are done to
        # the rows somebody ticked, not to a name typed into a form.
        "Create a relation from rows",
        # Not an action: a capability read off `SupportsBackup`, which is what
        # greys the Backups button out on a source that has no such program.
        "Copy the whole database out",
        # Declared with their installation condition (D120), never offered without it.
        *(
            f"{title} (when TimescaleDB is installed)" for title in (
                "Hypertable settings", "Change chunk interval", "Configure compression",
                "Set retention policy", "Remove retention policy",
                "Set compression policy", "Remove compression policy",
                "Set refresh policy", "Remove refresh policy", "Convert to hypertable",
                "Compress chunks", "Decompress chunks", "Drop chunks", "Merge chunks", "Merge chunks, reads going on", "Split a chunk",
                "Move chunks to a tablespace", "Reorder chunks by an index", "Detach chunks",
                "Attach a table as a chunk", "Skip chunks by a column", "Stop skipping chunks by a column",
            )
        ),
    }
    assert "Upload files" in files
    assert "Delete" in files


async def test_a_source_says_how_long_it_keeps_its_own_answers(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    types = {item["name"]: item for item in response.json()}
    # Read off the driver rather than listed, so a source that re-times itself
    # says so here in the same commit. The form shows these numbers beside the
    # field that would replace them (D105).
    assert types["postgres"]["cache_windows"] == {"catalog": 30.0, "fetch": 10.0}
    # Nothing rather than zeroes: a screen has to tell "kept for no time" from
    # "never cached at all", because only the first is something to change.
    assert types["file"]["cache_windows"] is None


async def test_every_type_reads_its_short_lists_from_its_guide_page(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The catalog and the guide say one thing, so the lists come from the page (D183)."""
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    for item in response.json():
        assert item["guide"] == f"source-{item['name']}"
        assert item["can_see"], item["name"]
    postgres = next(item for item in response.json() if item["name"] == "postgres")
    assert "Table data and columns" in postgres["can_change"]


async def test_a_russian_request_reads_the_types_in_russian(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The category and what a type can do are worded by the server (D226)."""
    response = await client.get(
        f"{BASE}/", headers={**normal_user_token_headers, "Accept-Language": "ru"}
    )

    types = {item["name"]: item for item in response.json()}
    assert types["postgres"]["category_title"] == "SQL-базы данных"
    titles = [c["title"] for c in types["postgres"]["capabilities"]]
    assert "Просматривать каталог" in titles
