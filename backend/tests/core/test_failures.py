"""A failure nobody caught is written down and answered with a ref (D184)."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.cors import CORSMiddleware

from app.core.failures import RecordFailures
from app.main import app as application


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("password=hunter2 went missing")

    # In the order main.py adds them.
    app.add_middleware(RecordFailures)
    app.add_middleware(CORSMiddleware, allow_origins=["http://front"])
    return app


async def test_an_uncaught_failure_is_answered_with_a_ref_and_logged_with_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR, logger="app.core.failures")
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={"Origin": "http://front"})

    assert response.status_code == 500
    ref = response.json()["detail"]["ref"]
    assert response.json()["detail"]["message"] == (
        f"Something went wrong on the server · ref {ref}"
    )
    assert "hunter2" not in response.text
    # A browser reads the sentence only when the answer names its origin.
    assert response.headers["access-control-allow-origin"] == "http://front"
    [record] = [one for one in caplog.records if one.name == "app.core.failures"]
    assert getattr(record, "ref", None) == ref
    assert record.exc_info is not None


def test_the_application_records_failures_inside_cors() -> None:
    order = [middleware.cls for middleware in application.user_middleware]

    assert order.index(CORSMiddleware) < order.index(RecordFailures)
