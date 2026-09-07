import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from app.adapters import registry
from app.adapters.features import SourceFeature, SourceFeatures
from app.adapters.protocol import ConnectionCheckResult
from app.core.config import settings

BASE = f"{settings.API_V1_STR}/connectors"


class FeatureOptions(BaseModel):
    url: str


class FeatureAdapter:
    def __init__(
        self, options: FeatureOptions, _context: registry.AdapterContext
    ) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="pong", latency_ms=1)

    async def source_features(self) -> SourceFeatures:
        return SourceFeatures(
            observed_at=datetime(2026, 9, 7, 12, 30, tzinfo=UTC),
            features=[
                SourceFeature(
                    code="timescaledb",
                    title="TimescaleDB",
                    installed_version="2.18.0",
                    state="available",
                )
            ],
        )


class PingAdapter:
    def __init__(
        self, options: FeatureOptions, _context: registry.AdapterContext
    ) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="pong", latency_ms=1)


async def _create_connector(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    adapter_name: str,
) -> str:
    created = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"features {uuid.uuid4()}",
            "adapter_type": adapter_name,
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200
    return str(created.json()["id"])


@pytest.mark.usefixtures("isolated_registry")
async def test_runtime_features_are_live_and_not_http_cached(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    registry.register(
        name="features",
        title="Features",
        category="sql",
        description="A source with runtime features.",
        options_schema=FeatureOptions,
        adapter_class=FeatureAdapter,
    )(FeatureAdapter)
    connector_id = await _create_connector(
        client, normal_user_token_headers, adapter_name="features"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/features", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "observed_at": "2026-09-07T12:30:00Z",
        "features": [
            {
                "code": "timescaledb",
                "title": "TimescaleDB",
                "installed_version": "2.18.0",
                "state": "available",
                "reason": None,
            }
        ],
    }


@pytest.mark.usefixtures("isolated_registry")
async def test_source_without_runtime_feature_capability_returns_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    registry.register(
        name="ping",
        title="Ping",
        category="sql",
        description="A source that can only be reached.",
        options_schema=FeatureOptions,
        adapter_class=PingAdapter,
    )(PingAdapter)
    connector_id = await _create_connector(
        client, normal_user_token_headers, adapter_name="ping"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/features", headers=normal_user_token_headers
    )

    assert response.status_code == 501
    assert response.json()["detail"] == {
        "message": "This source does not report runtime features",
        "error_kind": "config",
    }
