"""What the cluster lets this connection do, asked before a menu is drawn (D467).

`SelfSubjectAccessReview` for one verb on one resource in one namespace,
kept for a minute: a menu is drawn often and a role changes rarely. A review
the cluster will not answer counts as allowed, so the route's own refusal
still speaks when the action runs.
"""

import asyncio
import time
from dataclasses import dataclass

from app.adapters.kubernetes.session import KubernetesSession
from app.adapters.protocol import AdapterError

KEPT_SECONDS = 60.0


@dataclass(frozen=True)
class Asked:
    verb: str
    group: str
    resource: str
    namespace: str | None = None
    subresource: str = ""


class Reviews:
    def __init__(self, session: KubernetesSession) -> None:
        self._session = session
        self._kept: dict[Asked, tuple[float, bool]] = {}
        self._lock = asyncio.Lock()

    async def allows(self, asked: Asked) -> bool:
        async with self._lock:
            kept = self._kept.get(asked)
            if kept is not None and time.monotonic() - kept[0] < KEPT_SECONDS:
                return kept[1]
        allowed = await self._ask(asked)
        async with self._lock:
            self._kept[asked] = (time.monotonic(), allowed)
        return allowed

    async def all_allow(self, asked: list[Asked]) -> list[bool]:
        return list(await asyncio.gather(*(self.allows(one) for one in asked)))

    async def _ask(self, asked: Asked) -> bool:
        attributes: dict[str, str] = {
            "verb": asked.verb,
            "group": asked.group,
            "resource": asked.resource,
        }
        if asked.namespace:
            attributes["namespace"] = asked.namespace
        if asked.subresource:
            attributes["subresource"] = asked.subresource
        try:
            answer = await self._session.request(
                "POST",
                "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                body={
                    "apiVersion": "authorization.k8s.io/v1",
                    "kind": "SelfSubjectAccessReview",
                    "spec": {"resourceAttributes": attributes},
                },
                expected=(200, 201),
            )
            status = (answer.json() or {}).get("status") or {}
        except (AdapterError, ValueError):
            return True
        return bool(status.get("allowed"))
