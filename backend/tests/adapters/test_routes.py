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
        "Drop",
        "New schema",
        "Rename schema",
        "Move to schema",
        "Drop schema",
        "Install extension",
        "Remove extension",
    }
    assert "Upload files" in files
    assert "Delete" in files
