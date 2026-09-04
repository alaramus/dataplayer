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


async def test_cache_health_reports_the_default_without_making_redis_required(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{settings.API_V1_STR}/utils/cache-health/")

    assert response.status_code == 200
    assert response.json() == {
        "backend": "memory",
        "status": "healthy",
        "shared": False,
        "message": "Process-local cache is ready",
    }
