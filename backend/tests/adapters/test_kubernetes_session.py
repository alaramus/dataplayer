"""The API server's answers reduced to this repository's words (D464, D467),
against recorded answers rather than a cluster."""

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.kubernetes.adapter import KubernetesAdapter
from app.adapters.kubernetes.options import TokenOptions
from app.adapters.kubernetes.session import KubernetesSession, refused
from app.adapters.protocol import AdapterError, NodeNotFound

VERSION = {"major": "1", "minor": "33", "gitVersion": "v1.33.6+k3s1"}
FORBIDDEN = {
    "kind": "Status",
    "status": "Failure",
    "message": 'secrets is forbidden: User "system:serviceaccount:dp-test:dp-reader" cannot list resource "secrets"',
    "reason": "Forbidden",
    "code": 403,
}


def _options() -> TokenOptions:
    return TokenOptions(server="https://k8s.example:6443", token=SecretStr("the-token"))


def _transport(answer: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(answer)


async def test_a_token_is_sent_as_a_bearer_and_the_version_is_said() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=VERSION)

    adapter = KubernetesAdapter(_options(), transport=_transport(answer))
    result = await adapter.check_connection()
    assert result.ok and "v1.33.6+k3s1" in result.message
    assert seen[0].headers["Authorization"] == "Bearer the-token"
    assert seen[0].url.path == "/version"


@pytest.mark.parametrize(
    ("version", "words"),
    [({"major": "1", "minor": "26"}, "1.27 or newer"), ({"nothing": True}, "not as a Kubernetes")],
)
async def test_an_old_or_strange_server_is_refused(version: dict[str, object], words: str) -> None:
    adapter = KubernetesAdapter(_options(), transport=_transport(lambda _: httpx.Response(200, json=version)))
    result = await adapter.check_connection()
    assert not result.ok and words in result.message


async def test_a_minor_with_a_plus_is_read() -> None:
    answer = {"major": "1", "minor": "30+", "gitVersion": "v1.30.5-gke.1014001"}
    adapter = KubernetesAdapter(_options(), transport=_transport(lambda _: httpx.Response(200, json=answer)))
    assert (await adapter.check_connection()).ok


async def test_credentials_not_accepted_are_an_auth_failure() -> None:
    adapter = KubernetesAdapter(_options(), transport=_transport(lambda _: httpx.Response(401, json={})))
    result = await adapter.check_connection()
    assert result.error_kind == "auth"
    assert "did not accept" in result.message


def test_a_refusal_names_what_was_asked_and_never_the_identity() -> None:
    from app.adapters.kubernetes.session import Forbidden

    failure = refused(403, Forbidden("list", "secrets"), FORBIDDEN)
    assert failure.error_kind == "auth"
    assert "list secrets" in failure.message
    assert "serviceaccount" not in failure.message
    invalid = refused(
        422,
        None,
        {"message": "webhook says: password=hunter2", "details": {"causes": [{"field": "spec.replicas"}]}},
    )
    assert "spec.replicas" in invalid.message and "hunter2" not in invalid.message
    assert "changed" in refused(409, None, {}).message


async def test_an_object_that_is_gone_is_a_missing_node() -> None:
    discovery = {"resources": [{"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list"]}]}

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json=VERSION)
        if request.url.path == "/api/v1":
            return httpx.Response(200, json=discovery)
        if request.url.path == "/apis":
            return httpx.Response(200, json={"groups": []})
        return httpx.Response(404, json={"reason": "NotFound"})

    adapter = KubernetesAdapter(_options(), transport=_transport(answer))
    with pytest.raises(NodeNotFound):
        await adapter.path_to("ns/dp-test/o/core/pods/gone")
    # A kind the cluster does not serve is no node either.
    with pytest.raises(NodeNotFound):
        await adapter.list_children("ns/dp-test/k/apps/deployments")


async def test_a_list_is_read_page_by_page_and_the_server_text_never_reaches_a_caller() -> None:
    pages = {
        "": {"columnDefinitions": [{"name": "Name", "type": "string", "format": "name", "priority": 0}],
             "rows": [{"cells": ["a"], "object": {"metadata": {"name": "a"}}}], "metadata": {"continue": "next"}},
        "next": {"rows": [{"cells": ["b"], "object": {"metadata": {"name": "b"}}}], "metadata": {}},
    }
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json=VERSION)
        asked.append(request.headers["Accept"])
        token = request.url.params.get("continue", "")
        return httpx.Response(200, json=pages[token])

    session = KubernetesSession(_options(), None, _transport(answer))
    from app.adapters.kubernetes.discovery import Resource
    from app.adapters.kubernetes.tables import read_table

    listed = await read_table(session, Resource("", "v1", "pods", "Pod", True, frozenset()), "dp-test")
    assert [name for name, _, _ in listed.names] == ["a", "b"]
    assert all("as=Table" in one for one in asked)

    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json=VERSION)
        return httpx.Response(500, content=json.dumps({"message": "etcd at 10.0.0.5 said no"}).encode())

    failing = KubernetesAdapter(_options(), transport=_transport(broken))
    with pytest.raises(AdapterError) as failure:
        await failing.list_children("ns/dp-test")
    assert "10.0.0.5" not in failure.value.message
