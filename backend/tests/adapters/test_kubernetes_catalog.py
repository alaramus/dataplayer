"""Node ids, the cluster's tables, selectors, logs and a Secret kept hidden
(D465, D466), without a cluster."""

import json

import pytest

from app.adapters.kubernetes.card import as_yaml, object_view, redacted
from app.adapters.kubernetes.catalog import (
    kind_id,
    object_id,
    page_id,
    parse,
)
from app.adapters.kubernetes.discovery import Resource, resources_in
from app.adapters.kubernetes.tables import event_rows, log_rows, selector_of, table_of

PODS = Resource("", "v1", "pods", "Pod", True, frozenset({"get", "list"}))
SECRETS = Resource("", "v1", "secrets", "Secret", True, frozenset({"get", "list"}))
DEPLOYMENTS = Resource("apps", "v1", "deployments", "Deployment", True, frozenset({"get", "list"}))
NODES = Resource("", "v1", "nodes", "Node", False, frozenset({"get", "list"}))


def test_ids_name_what_they_say_and_round_trip() -> None:
    assert parse(kind_id("dp-test", DEPLOYMENTS)).resource == "deployments"
    named = parse(object_id("dp-test", "", "pods", "web-1"))
    assert (named.namespace, named.group, named.resource, named.name) == ("dp-test", "", "pods", "web-1")
    scoped = parse(object_id(None, "", "nodes", "k3s"))
    assert scoped.top == "scoped" and scoped.namespace is None
    logs = parse(page_id(object_id("dp-test", "", "pods", "web-1"), "logs", "echo"))
    assert (logs.view, logs.container) == ("logs", "echo")
    assert parse("ns/*/k/apps/deployments").namespace == "*"
    assert parse("ns/dp-test/s/workloads").section == "workloads"
    assert parse("cluster/overview").report == "overview"


@pytest.mark.parametrize(
    "node_id",
    [
        "ns/Bad_NS",
        "ns/dp-test/k/apps",
        "ns/dp-test/o/apps/deployments/../etc",
        "ns/dp-test/o/apps/deployments/web/yaml",
        "ns/dp-test/o/core/pods/web/logs",
        "ns/dp-test/o/core/pods/web/logs/Not_A_Label",
        "ns/*/o/core/pods/web",
        "ns/dp-test/s/nowhere",
        "elsewhere",
        "cluster/../x",
    ],
)
def test_an_id_this_source_never_made_is_refused(node_id: str) -> None:
    with pytest.raises(ValueError, match="Not a node"):
        parse(node_id)


def test_discovery_keeps_kinds_that_list_and_get_and_no_subresources() -> None:
    body = {
        "resources": [
            {"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list", "watch"]},
            {"name": "pods/log", "kind": "Pod", "namespaced": True, "verbs": ["get"]},
            {"name": "bindings", "kind": "Binding", "namespaced": True, "verbs": ["create"]},
            {"name": "events", "kind": "Event", "namespaced": True, "verbs": ["get", "list"]},
        ]
    }
    found = resources_in("", "v1", body)
    assert [one.resource for one in found] == ["pods"]
    assert found[0].section == "workloads"
    assert Resource("example.com", "v1", "widgets", "Widget", True, frozenset()).section == "other"
    assert PODS.base("dp-test") == "/api/v1/namespaces/dp-test/pods"
    assert DEPLOYMENTS.path(None, "web") == "/apis/apps/v1/deployments/web"
    assert NODES.base("dp-test") == "/api/v1/nodes"


def test_the_clusters_table_becomes_columns_with_a_creation_time() -> None:
    answer = {
        "columnDefinitions": [
            {"name": "Name", "type": "string", "format": "name", "priority": 0},
            {"name": "Ready", "type": "string", "format": "", "priority": 0},
            {"name": "Status", "type": "string", "format": "", "priority": 0},
            {"name": "Restarts", "type": "integer", "format": "", "priority": 0},
            {"name": "Age", "type": "string", "format": "", "priority": 0},
            {"name": "IP", "type": "string", "format": "", "priority": 1},
        ],
        "rows": [
            {
                "cells": ["web-1", "1/1", "Running", 0, "5m", "10.42.0.9"],
                "object": {"metadata": {"name": "web-1", "namespace": "dp-test", "creationTimestamp": "2026-11-28T06:48:21Z"}},
            }
        ],
    }
    listed = table_of([answer], every_namespace=True, cut=False)
    assert [column.name for column in listed.columns] == [
        "Namespace", "Name", "Ready", "Status", "Restarts", "IP", "Created"
    ]
    assert [column.type.category for column in listed.columns][4] == "number"
    assert listed.rows == [["dp-test", "web-1", "1/1", "Running", "0", "10.42.0.9", "2026-11-28T06:48:21Z"]]
    assert listed.summaries == ["1/1 · Running"]
    assert listed.names == [("web-1", "dp-test", "2026-11-28T06:48:21Z")]


def test_a_selector_is_written_as_the_api_reads_it() -> None:
    assert selector_of({"app": "web", "tier": "front"}) == "app=web,tier=front"
    assert (
        selector_of(
            {
                "matchLabels": {"app": "web"},
                "matchExpressions": [
                    {"key": "env", "operator": "In", "values": ["a", "b"]},
                    {"key": "old", "operator": "DoesNotExist"},
                ],
            }
        )
        == "app=web,env in (a,b),!old"
    )
    assert selector_of(None) is None
    assert selector_of({}) is None


def test_logs_read_newest_first_with_their_times() -> None:
    rows = log_rows("2026-11-28T06:49:21.5Z line 1\n2026-11-28T06:49:23.5Z line 2\nno stamp here")
    assert rows[0] == [None, "no stamp here"]
    assert rows[1] == ["2026-11-28T06:49:23.5Z", "line 2"]


def test_events_are_newest_first() -> None:
    rows = event_rows(
        {
            "items": [
                {"lastTimestamp": "2026-11-28T06:00:00Z", "type": "Normal", "involvedObject": {"kind": "Pod", "name": "a"}},
                {"lastTimestamp": "2026-11-28T07:00:00Z", "type": "Warning", "reason": "BackOff", "involvedObject": {"kind": "Pod", "name": "b"}},
            ]
        }
    )
    assert [row[3] for row in rows] == ["Pod/b", "Pod/a"]


SECRET = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {
        "name": "password",
        "namespace": "dp-test",
        "managedFields": [{"manager": "kubectl"}],
        "annotations": {
            "kubectl.kubernetes.io/last-applied-configuration": '{"data":{"password":"c2VjcmV0LXZhbHVl"}}',
            "note": "kept",
        },
    },
    "type": "Opaque",
    "data": {"password": "c2VjcmV0LXZhbHVl"},
    "stringData": {"token": "plain-secret"},
}


def test_a_secrets_values_never_leave_in_any_representation() -> None:
    shown = redacted(SECRETS, SECRET)
    text = as_yaml(SECRETS, SECRET) + json.dumps(shown) + object_view(SECRETS, SECRET).model_dump_json()
    for leaked in ("c2VjcmV0LXZhbHVl", "secret-value", "plain-secret", "last-applied"):
        assert leaked not in text
    assert "managedFields" not in text
    assert "12 bytes" in as_yaml(SECRETS, SECRET)
    assert shown["metadata"]["annotations"] == {"note": "kept"}
    # The object read stays as it was.
    assert SECRET["data"] == {"password": "c2VjcmV0LXZhbHVl"}


def test_another_kinds_data_is_shown_as_it_is() -> None:
    config = {"metadata": {"name": "settings"}, "data": {"greeting": "hello"}}
    configmaps = Resource("", "v1", "configmaps", "ConfigMap", True, frozenset())
    assert "hello" in as_yaml(configmaps, config)
    assert "hello" in object_view(configmaps, config).model_dump_json()


def test_a_pods_view_says_its_state_and_containers() -> None:
    pod = {
        "metadata": {"name": "web-1", "namespace": "dp-test"},
        "spec": {"containers": [{"name": "echo", "image": "busybox:1.37"}], "nodeName": "k3s"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {"name": "echo", "ready": False, "restartCount": 4, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}
            ],
        },
    }
    view = object_view(PODS, pod)
    assert view.header.state is not None
    assert (view.header.state.word, view.header.state.tone) == ("CrashLoopBackOff", "bad")
    assert "busybox:1.37" in view.model_dump_json()


def test_a_workloads_template_shows_no_states_it_cannot_have() -> None:
    deployment = {
        "metadata": {"name": "web", "namespace": "dp-test"},
        "spec": {
            "replicas": 2,
            "selector": {"matchLabels": {"app": "web"}},
            "template": {"spec": {"containers": [{"name": "echo", "image": "busybox:1.37"}]}},
        },
        "status": {"readyReplicas": 2},
    }
    view = object_view(DEPLOYMENTS, deployment)
    containers = next(
        block for block in view.blocks if getattr(block, "title", "") == "Containers"
    )
    assert containers.blocks[0].columns == ["Name", "Image", "Ports"]  # type: ignore[union-attr] # a table
