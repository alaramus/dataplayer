"""What a client may know about the services this server can start."""

from httpx import AsyncClient

from app.core.config import settings
from app.main import app
from app.services.engine import SWITCHED_OFF_MESSAGE
from tests.utils.service_engine import FakeEngine, engine_of

BASE = f"{settings.API_V1_STR}/services"


async def test_the_templates_are_listed_with_what_each_one_becomes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/templates", headers=normal_user_token_headers)

    assert response.status_code == 200
    postgres = next(item for item in response.json() if item["key"] == "postgres")
    assert postgres["title"] == "PostgreSQL"
    assert postgres["image"] == "postgres:18"
    assert postgres["adapter_type"] == "postgres"
    # The words for a source type are the server's, so a screen showing what a
    # service becomes does not keep a second name for it.
    assert postgres["adapter_title"] == "PostgreSQL"
    # What a person will not be asked for, and what they may name when they
    # want to. The password is on the first list and never on the second: a
    # chosen one would have to be written down between the request and the job
    # that uses it (D4).
    assert postgres["generated"] == ["password"]
    assert postgres["choosable"] == ["user", "database"]
    assert postgres["offers_sample_data"] is True


async def test_nothing_about_the_container_is_published(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Publishing the environment or the volume would invite the belief that a
    request could steer them."""
    response = await client.get(f"{BASE}/templates", headers=normal_user_token_headers)

    listed = response.json()[0]
    assert set(listed) == {
        "key",
        "title",
        "description",
        "image",
        "container_port",
        "adapter_type",
        "adapter_title",
        "generated",
        # What a person may name themselves, which is names inside the server
        # rather than anything about the container that runs it.
        "choosable",
        "offers_sample_data",
        # Not about the container: about whether this server could start one.
        "available",
        "unavailable_reason",
    }


async def test_a_stranger_is_not_told_what_this_server_can_start(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{BASE}/templates")

    assert response.status_code == 401


async def test_the_listing_says_whether_one_could_be_started_now(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A screen that offers what will be refused is a screen that lies (D82).

    In a test environment services are switched off, which is one of the two
    reasons a server may have; the other is that no runtime answers.
    """
    response = await client.get(f"{BASE}/templates", headers=normal_user_token_headers)

    postgres = next(item for item in response.json() if item["key"] == "postgres")
    assert postgres["available"] is False
    assert postgres["unavailable_reason"] == SWITCHED_OFF_MESSAGE


async def test_with_a_runtime_the_same_listing_offers_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    with engine_of(app, FakeEngine()):
        response = await client.get(
            f"{BASE}/templates", headers=normal_user_token_headers
        )

    postgres = next(item for item in response.json() if item["key"] == "postgres")
    assert postgres["available"] is True
    assert postgres["unavailable_reason"] is None
