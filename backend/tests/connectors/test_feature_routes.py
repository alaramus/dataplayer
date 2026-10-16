import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

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
    client: AsyncClient, normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
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
        # A source that says what it is running fills this in; this one does
        # not, and the field is there either way.
        "server_version": None,
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
    absent = SourceFeatures(
        observed_at=datetime(2026, 9, 7, 12, 31, tzinfo=UTC),
        features=[SourceFeature(code="timescaledb", title="TimescaleDB", state="absent")],
    )
    discovery = AsyncMock(return_value=absent)
    monkeypatch.setattr(FeatureAdapter, "source_features", discovery)
    refreshed = await client.get(
        f"{BASE}/{connector_id}/features", headers=normal_user_token_headers
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["cache-control"] == "no-store"
    assert refreshed.json() == absent.model_dump(mode="json")
    discovery.assert_awaited_once()


@pytest.mark.usefixtures("isolated_registry")
async def test_feature_discovery_requires_current_read_access_and_enabled_connector(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry.register(
        name="features", title="Features", category="sql",
        description="A source with runtime features.",
        options_schema=FeatureOptions, adapter_class=FeatureAdapter,
    )(FeatureAdapter)
    owner = normal_user_token_headers
    reader = superuser_token_headers
    connector_id = await _create_connector(client, owner, adapter_name="features")
    path = f"{BASE}/{connector_id}/features"
    discovery = AsyncMock(return_value=SourceFeatures(
        observed_at=datetime(2026, 9, 7, tzinfo=UTC),
        features=[SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available",
            installed_version="2.18.0",
        )],
    ))
    monkeypatch.setattr(FeatureAdapter, "source_features", discovery)
    # Administration does not grant access to somebody else's source (D33).
    assert (await client.get(path, headers=reader)).status_code == 404
    discovery.assert_not_awaited()
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=reader)
    assert me.status_code == 200
    reader_id = me.json()["id"]
    granted = await client.put(
        f"{BASE}/{connector_id}/grants", headers=owner,
        json={"user_id": reader_id, "access": "read"},
    )
    assert granted.status_code == 200
    assert (await client.get(path, headers=reader)).status_code == 200
    discovery.assert_awaited_once()
    discovery.reset_mock()
    revoked = await client.delete(
        f"{BASE}/{connector_id}/grants/{reader_id}", headers=owner,
    )
    assert revoked.status_code == 200
    assert (await client.get(path, headers=reader)).status_code == 404
    discovery.assert_not_awaited()
    disabled = await client.patch(
        f"{BASE}/{connector_id}", headers=owner, json={"enabled": False},
    )
    assert disabled.status_code == 200
    response = await client.get(path, headers=owner)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "connectors.disabled"
    discovery.assert_not_awaited()


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
        "code": "connectors.no_runtime_features",
        "params": {},
        "message": "This source does not report runtime features",
        "error_kind": "config",
    }
