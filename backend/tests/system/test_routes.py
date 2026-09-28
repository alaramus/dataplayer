from httpx import AsyncClient

from app.core.config import settings


async def test_server_info_is_public_and_identifies_the_client_contract(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{settings.API_V1_STR}/utils/server-info")

    assert response.status_code == 200
    assert response.json() == {"product": "dataplayer", "client_api_version": 1}


async def test_server_info_is_readable_from_the_configured_frontend(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/utils/server-info",
        headers={"Origin": settings.FRONTEND_HOST},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.FRONTEND_HOST


async def test_cache_health_is_not_readable_without_an_operator(
    client: AsyncClient,
) -> None:
    """What the installation runs is not anonymous information."""
    response = await client.get(f"{settings.API_V1_STR}/utils/cache-health/")

    assert response.status_code == 401


async def test_cache_health_reports_the_default_without_making_redis_required(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/utils/cache-health/",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    measurements = body.pop("measurements")
    assert body == {
        "backend": "memory",
        "status": "healthy",
        "shared": False,
        "message": "Process-local cache is ready",
    }
    assert set(measurements) == {
        "hits",
        "misses",
        "coalesced",
        "refreshed",
        "bypasses",
        "invalidations",
        "failures",
    }
    assert all(value >= 0 for value in measurements.values())


async def test_the_log_is_a_superusers_to_read(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    """D184: it names every request and every failure of the installation."""
    url = f"{settings.API_V1_STR}/logs/"
    refused = await client.get(url, headers=normal_user_token_headers)
    allowed = await client.get(url, headers=superuser_token_headers)

    assert refused.status_code == 403
    assert allowed.status_code == 200
    assert set(allowed.json()) == {"kept", "entries", "more"}
