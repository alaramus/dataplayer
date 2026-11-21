"""Pull and commit, which take minutes, as owned jobs of one target (D412, D123).

Pull reads the daemon's JSON-lines stream to its end: an error arrives inside
a 200. A reference the registry answers 401 or 404 to is said as one sentence:
it is not there, or it is private, and private registries are not supported.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import Action, ActionPreview, ActionRefused, ActsOn
from app.adapters.catalog import NodeKind
from app.adapters.docker.actions import containers_of
from app.adapters.docker.inventory import name_of
from app.adapters.docker.session import DockerSession, segment
from app.adapters.docker_api.client import EngineRefused, EngineUnreachable
from app.adapters.docker_api.frames import stream_failed
from app.adapters.layout import layout
from app.adapters.operations import (
    ObservedState,
    OperationPlan,
    OperationTarget,
    UnitOutcome,
)
from app.adapters.protocol import AdapterError
from app.core.access import Access
from app.core.translation import N_, say

PULL_SECONDS = 900.0
COMMIT_SECONDS = 900.0

# Docker's reference grammar, without the parts a pull from a public registry
# never needs: an optional registry host (with a dot, a port or `localhost`),
# lowercase path components, an optional tag, an optional digest.
_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_DOMAIN = r"(?:(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+(?::[0-9]+)?|localhost(?::[0-9]+)?|[a-zA-Z0-9-]+:[0-9]+)"
_TAG = r"[\w][\w.-]{0,127}"
REFERENCE = re.compile(
    rf"^(?:{_DOMAIN}/)?{_COMPONENT}(?:/{_COMPONENT})*(?::{_TAG})?(?:@sha256:[0-9a-f]{{64}})?$"
)
REPOSITORY = re.compile(rf"^(?:{_DOMAIN}/)?{_COMPONENT}(?:/{_COMPONENT})*$")
TAG = re.compile(rf"^{_TAG}$")


def split_reference(reference: str) -> tuple[str, str]:
    """What `/images/create` takes: the repository, and a tag or a digest."""
    name, at, digest = reference.partition("@")
    slash = name.rfind("/")
    colon = name.rfind(":")
    repository, tag = (name[:colon], name[colon + 1 :]) if colon > slash else (name, "")
    if at:
        return f"{repository}@{digest}", ""
    return repository, tag or "latest"


def _target(text: str) -> OperationTarget:
    shown = text if len(text) <= 63 else text[:62] + "…"
    return OperationTarget(schema_name="docker", name=shown)


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


class PullParams(BaseModel):
    reference: str = Field(
        max_length=255,
        title=N_("Image"),
        description=N_("A public image: a name, a tag, a registry before it if not Docker Hub"),
        examples=["nginx:1.27", "ghcr.io/owner/app:2.1"],
        json_schema_extra=layout(),
    )

    @field_validator("reference")
    @classmethod
    def _grammar(cls, text: str) -> str:
        text = text.strip()
        if not REFERENCE.match(text):
            raise ValueError(say("Not an image reference Docker would take"))
        return text


class CommitParams(BaseModel):
    repository: str = Field(
        max_length=255,
        title=N_("Repository"),
        description=N_("Lowercase, parts separated by /"),
        examples=["backups/web"],
        json_schema_extra=layout(row="name"),
    )
    tag: str = Field(
        default="latest",
        max_length=128,
        title=N_("Tag"),
        json_schema_extra=layout(row="name"),
    )

    @field_validator("repository")
    @classmethod
    def _repository(cls, text: str) -> str:
        if not REPOSITORY.match(text):
            raise ValueError(say("Not a repository name Docker would take"))
        return text

    @field_validator("tag")
    @classmethod
    def _tag(cls, text: str) -> str:
        if not TAG.match(text):
            raise ValueError(say("Not a tag Docker would take"))
        return text


async def _has_image(session: DockerSession, reference: str) -> bool:
    status, _ = await session.send(
        "GET", f"/images/{segment(reference)}/json", expected=(200, 404)
    )
    return status == 200


class PullImage(Action[PullParams]):
    name: ClassVar[str] = "docker_pull"
    title: ClassVar[str] = N_("Pull image")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = PullParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    def _level(self, node_id: str | None) -> None:
        if node_id != "images":
            raise ActionRefused("not_applicable", say("Pull from Images"))

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        self._level(node_id)
        here = await _has_image(self._session, params.reference)
        return ActionPreview(
            summary=say("{reference} will be pulled as a job", reference=params.reference),
            items=[
                say("It is here already; a newer one replaces the tag if there is one")
                if here
                else say("It is not here yet"),
                say("Only public images: private registries are not supported yet"),
            ],
            fingerprint=_fingerprint("pull", params.reference),
        )

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str
    ) -> OperationPlan:
        params = self._validated(raw)
        self._level(node_id)
        unit = _fingerprint("pull", params.reference)
        if unit != reviewed_fingerprint:
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        return OperationPlan(
            summary=say("Pull {reference}", reference=params.reference),
            unit_fingerprint=unit,
            targets=(_target(params.reference),),
        )

    async def run_unit(
        self,
        node_id: str | None,
        raw: Mapping[str, Any],
        unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome:
        del node_id, target
        params = self._validated(raw)
        if unit_fingerprint != _fingerprint("pull", params.reference):
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        repository, tag = split_reference(params.reference)
        query = {"fromImage": repository, **({"tag": tag} if tag else {})}
        engine = await self._session.engine()
        try:
            async with engine.stream(
                "POST", "/images/create", params=query, seconds=PULL_SECONDS
            ) as response:
                async for line in response.aiter_lines():
                    if stream_failed(line):
                        raise ActionRefused(
                            "conflict", say("The daemon could not pull {reference}", reference=params.reference)
                        )
        except EngineRefused as refused:
            if refused.status in {401, 403, 404}:
                raise ActionRefused(
                    "not_applicable",
                    say(
                        "{reference} is not there, or it is private: private registries are not supported yet",
                        reference=params.reference,
                    ),
                ) from None
            raise ActionRefused("conflict", say("The Docker server could not do that")) from None
        except EngineUnreachable:
            # The pull may have finished on the daemon without our hearing it.
            raise AdapterError(
                "network", say("The Docker server stopped answering through the SSH connection")
            ) from None
        return "completed"

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget]
    ) -> list[ObservedState]:
        del node_id
        params = self._validated(raw)
        here = await _has_image(self._session, params.reference)
        return ["as_requested" if here else "unchanged" for _ in targets]


class CommitContainer(Action[CommitParams]):
    name: ClassVar[str] = "docker_commit"
    title: ClassVar[str] = N_("Commit to an image")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"container"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = CommitParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def _container(self, node_id: str | None) -> dict[str, Any]:
        found = await containers_of(self._session, node_id)
        if len(found) != 1 or not (node_id or "").startswith("container:"):
            raise ActionRefused("not_applicable", say("Choose one container"))
        return found[0]

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        one = await self._container(node_id)
        reference = f"{params.repository}:{params.tag}"
        taken = await _has_image(self._session, reference)
        items = [say("Its volumes are not part of the image")]
        if taken:
            items.append(say("{reference} exists; the tag moves to the new image", reference=reference))
        if one.get("State") == "running":
            items.append(say("It is paused while the image is made"))
        return ActionPreview(
            summary=say(
                "{name} will be committed to {reference} as a job",
                name=name_of(one),
                reference=reference,
            ),
            items=items,
            fingerprint=_fingerprint("commit", str(one["Id"]), reference),
        )

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str
    ) -> OperationPlan:
        params = self._validated(raw)
        one = await self._container(node_id)
        reference = f"{params.repository}:{params.tag}"
        unit = _fingerprint("commit", str(one["Id"]), reference)
        if unit != reviewed_fingerprint:
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        return OperationPlan(
            summary=say("Commit {name} to {reference}", name=name_of(one), reference=reference),
            unit_fingerprint=unit,
            targets=(_target(reference),),
        )

    async def run_unit(
        self,
        node_id: str | None,
        raw: Mapping[str, Any],
        unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome:
        del target
        params = self._validated(raw)
        one = await self._container(node_id)
        reference = f"{params.repository}:{params.tag}"
        if unit_fingerprint != _fingerprint("commit", str(one["Id"]), reference):
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        await self._session.send(
            "POST",
            "/commit",
            {"container": str(one["Id"]), "repo": params.repository, "tag": params.tag},
            expected=(201,),
            seconds=COMMIT_SECONDS,
        )
        return "completed"

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget]
    ) -> list[ObservedState]:
        del node_id
        params = self._validated(raw)
        here = await _has_image(self._session, f"{params.repository}:{params.tag}")
        return ["as_requested" if here else "unchanged" for _ in targets]


def job_actions(session: DockerSession) -> list[Action[Any]]:
    return [PullImage(session), CommitContainer(session)]
