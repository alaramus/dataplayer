from httpx import AsyncClient

from app.core.config import settings


async def test_a_browser_may_read_the_download_filename_across_origins(
    client: AsyncClient,
) -> None:
    """The filename of a saved page travels in a header, not in the body.

    Content-Disposition is not safelisted, so without this the page reads
    nothing and has to guess a name — but only when the frontend is served
    from its own port, which is exactly the arrangement tests run against.
    """
    response = await client.get(
        f"{settings.API_V1_STR}/openapi.json",
        headers={"Origin": settings.FRONTEND_HOST},
    )

    exposed = {
        name.strip().lower()
        for name in response.headers.get("access-control-expose-headers", "").split(",")
    }
    assert "content-disposition" in exposed
