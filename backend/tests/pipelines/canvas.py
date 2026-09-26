"""A pipeline of the test user, drawn and saved as the screen does it."""

import uuid
from typing import Any

from httpx import AsyncClient, Response

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/pipelines"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def connector(client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={"name": f"{adapter_type} {uuid.uuid4()}", "adapter_type": adapter_type, "options": options},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def card(
    connector_id: str, rows: list[tuple[str | None, str, str | None]], x: float = 0, name: str = "a connection"
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "connector_name": name,
        "x": x,
        "y": 0,
        "rows": [{"node_id": node, "label": label, "kind": kind, "trail": []} for node, label, kind in rows],
    }


def link(
    source: dict[str, Any], source_node: str | None, target: dict[str, Any], target_node: str | None, kind: str, **choices: Any
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source": {"card_id": source["id"], "node_id": source_node},
        "target": {"card_id": target["id"], "node_id": target_node},
        "kind": kind,
        "title": kind.replace("_", " "),
        **choices,
    }


def end(card: dict[str, Any], node_id: str | None = None, made_by: dict[str, Any] | None = None) -> dict[str, Any]:
    """A row of a card: a ticked node, or what a link makes (D178)."""
    return {"card_id": card["id"], "node_id": node_id, "made_by": None if made_by is None else made_by["id"]}


def joined(source: dict[str, Any], target: dict[str, Any], kind: str, **choices: Any) -> dict[str, Any]:
    """A link between two ends as `end` names them."""
    return {"id": str(uuid.uuid4()), "source": source, "target": target, "kind": kind, "title": kind.replace("_", " "), **choices}


class Canvas:
    """One pipeline of the test user, saved whole as the screen saves it."""

    def __init__(self, client: AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.id = ""
        self.version = 0

    async def make(self) -> Canvas:
        made = await self.client.post(BASE, headers=self.headers, json={"name": "Nightly"})
        assert made.status_code == 200, made.text
        self.id, self.version = made.json()["id"], made.json()["version"]
        return self

    async def save(self, cards: list[dict[str, Any]], links: list[dict[str, Any]]) -> Response:
        answer = await self.client.put(
            f"{BASE}/{self.id}",
            headers=self.headers,
            json={"name": "Nightly", "version": self.version, "cards": cards, "links": links},
        )
        if answer.status_code == 200:
            self.version = answer.json()["version"]
        return answer

    async def run(self) -> Response:
        return await self.client.post(f"{BASE}/{self.id}/run", headers=self.headers)

    async def last(self) -> Any:
        answer = await self.client.get(f"{BASE}/{self.id}/run", headers=self.headers)
        assert answer.status_code == 200, answer.text
        return answer.json()["run"]

    async def outcomes(self) -> dict[str, tuple[str, str | None]]:
        """What each link did in the last run, by link id."""
        last = await self.last()
        return {one["link_id"]: (one["outcome"], one["message"]) for one in last["links"]}

    async def offers(self, source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        """What can go between two ends, by kind."""
        answer = await self.client.post(
            f"{BASE}/{self.id}/offers", headers=self.headers, json={"source": source, "target": target}
        )
        assert answer.status_code == 200, answer.text
        return {one["kind"]: one for one in answer.json()["offers"]}

    async def hint(self, card_id: str | None = None) -> dict[str, Any]:
        answer = await self.client.post(f"{BASE}/{self.id}/hint", headers=self.headers, json={"card_id": card_id})
        assert answer.status_code == 200, answer.text
        result: dict[str, Any] = answer.json()
        return result
