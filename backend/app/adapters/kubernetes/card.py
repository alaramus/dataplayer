"""An object as a view of its document (D466, D419–D421), and as YAML.

Plain functions of the object the source already read. Every object shows its
metadata, its conditions and its owners; the kinds a person opens most also
show what they are read for. A Secret's values never leave here: its view
lists the keys and their sizes, and its YAML and JSON carry sizes in place of
values, `last-applied-configuration` (which holds a copy) left out.
"""

import base64
import binascii
import copy
from typing import Any

import yaml

from app.adapters.kubernetes.discovery import Resource
from app.adapters.kubernetes.tables import instant
from app.adapters.views import (
    BooleanValue,
    BytesValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    NoticeBlock,
    NumberValue,
    SectionBlock,
    StateValue,
    Tone,
    ViewBlock,
    ViewField,
    ViewHeader,
    ViewPair,
    ViewValue,
    chips,
    code,
    moment,
    pairs,
    table,
    text,
)
from app.core.translation import say

LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"
_GOOD = {"Running", "Succeeded", "Bound", "Active", "Ready", "Available", "Complete", "True"}
_BAD = {"Failed", "Lost", "NotReady", "CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull"}
_BUSY = {"Pending", "ContainerCreating", "Terminating", "Progressing"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def tone_of(word: str) -> Tone:
    if word in _GOOD:
        return "good"
    if word in _BAD:
        return "bad"
    if word in _BUSY:
        return "busy"
    return "neutral"


def word_value(value: Any) -> ViewValue:
    return EmptyValue() if value in (None, "", []) else text(str(value))


def at_value(value: Any) -> ViewValue:
    return moment(instant(value))


def _size_of(value: Any) -> int:
    try:
        return len(base64.b64decode(str(value), validate=True))
    except (binascii.Error, ValueError):
        return len(str(value))


def redacted(resource: Resource, body: dict[str, Any]) -> dict[str, Any]:
    """The object as shown: `managedFields` gone, a Secret's values sizes."""
    shown = copy.deepcopy(body)
    metadata = as_dict(shown.get("metadata"))
    metadata.pop("managedFields", None)
    if resource.key == "/secrets":
        annotations = as_dict(metadata.get("annotations"))
        annotations.pop(LAST_APPLIED, None)
        for field in ("data", "stringData"):
            values = shown.get(field)
            if isinstance(values, dict):
                shown[field] = {
                    key: say("<{count} bytes, hidden>", count=_size_of(value) if field == "data" else len(str(value)))
                    for key, value in values.items()
                }
    return shown


def as_yaml(resource: Resource, body: dict[str, Any]) -> str:
    return str(yaml.safe_dump(redacted(resource, body), sort_keys=False, allow_unicode=True, width=120))


def state_of(resource: Resource, body: dict[str, Any]) -> StateValue | None:
    status = as_dict(body.get("status"))
    key = resource.key
    if key == "/pods":
        word = _pod_word(body)
    elif key == "/nodes":
        ready = _condition(status, "Ready")
        word = "Ready" if ready == "True" else "NotReady"
    elif key in ("apps/deployments", "apps/statefulsets", "apps/replicasets"):
        wanted = as_dict(body.get("spec")).get("replicas", 1)
        have = status.get("readyReplicas", 0) or 0
        return StateValue(word=f"{have}/{wanted}", tone="good" if have == wanted else "busy")
    elif key == "apps/daemonsets":
        wanted = status.get("desiredNumberScheduled", 0) or 0
        have = status.get("numberReady", 0) or 0
        return StateValue(word=f"{have}/{wanted}", tone="good" if have == wanted else "busy")
    elif key == "batch/jobs":
        word = "Complete" if _condition(status, "Complete") == "True" else (
            "Failed" if _condition(status, "Failed") == "True" else "Running"
        )
    elif isinstance(status.get("phase"), str):
        word = status["phase"]
    else:
        return None
    if as_dict(body.get("metadata")).get("deletionTimestamp"):
        word = "Terminating"
    return StateValue(word=word, tone=tone_of(word))


def _condition(status: dict[str, Any], kind: str) -> str | None:
    for one in as_list(status.get("conditions")):
        if isinstance(one, dict) and one.get("type") == kind:
            return str(one.get("status"))
    return None


def _pod_word(body: dict[str, Any]) -> str:
    """What `kubectl get pods` says in Status: a waiting or terminated reason
    of a container before the pod's phase."""
    status = as_dict(body.get("status"))
    for state in as_list(status.get("containerStatuses")):
        current = as_dict(as_dict(state).get("state"))
        reason = as_dict(current.get("waiting")).get("reason") or as_dict(current.get("terminated")).get("reason")
        if reason and reason not in ("Completed",):
            return str(reason)
    return str(status.get("phase") or "Unknown")


def _metadata_block(resource: Resource, body: dict[str, Any]) -> FieldsBlock:
    """The kind is not a field: the header's subtitle says it, and a kind's
    own `type` (a Secret's, a Service's) would stand beside it as a second
    "Type" in languages that name both alike."""
    metadata = as_dict(body.get("metadata"))
    namespace = metadata.get("namespace")
    owners = [
        f"{as_dict(one).get('kind')}/{as_dict(one).get('name')}"
        for one in as_list(metadata.get("ownerReferences"))
    ]
    fields = [
        ViewField(label=say("API version"), value=text(str(body.get("apiVersion") or resource.version))),
        ViewField(label=say("Namespace"), value=word_value(namespace)),
        ViewField(label=say("Created"), value=at_value(metadata.get("creationTimestamp"))),
        ViewField(label=say("UID"), value=code(str(metadata.get("uid") or ""))),
    ]
    if owners:
        fields.append(ViewField(label=say("Owned by"), value=chips(owners)))
    return FieldsBlock(fields=fields)


def _labels_section(body: dict[str, Any]) -> list[ViewBlock]:
    metadata = as_dict(body.get("metadata"))
    blocks: list[ViewBlock] = []
    labels = as_dict(metadata.get("labels"))
    if labels:
        blocks.append(
            SectionBlock(
                title=say("Labels"),
                blocks=[pairs([ViewPair(name=str(k), value=str(v)) for k, v in sorted(labels.items())])],
            )
        )
    annotations = {k: v for k, v in as_dict(metadata.get("annotations")).items() if k != LAST_APPLIED}
    if annotations:
        blocks.append(
            SectionBlock(
                title=say("Annotations"),
                collapsed=True,
                blocks=[pairs([ViewPair(name=str(k), value=str(v)) for k, v in sorted(annotations.items())])],
            )
        )
    return blocks


def _conditions(body: dict[str, Any]) -> list[ViewBlock]:
    rows: list[list[ViewValue]] = []
    for one in as_list(as_dict(body.get("status")).get("conditions")):
        one = as_dict(one)
        status = str(one.get("status") or "")
        rows.append(
            [
                text(str(one.get("type") or "")),
                StateValue(word=status or "—", tone="good" if status == "True" else "neutral"),
                word_value(one.get("reason")),
                word_value(one.get("message")),
                at_value(one.get("lastTransitionTime")),
            ]
        )
    if not rows:
        return []
    return [
        SectionBlock(
            title=say("Conditions"),
            blocks=[table([say("Type"), say("Status"), say("Reason"), say("Message"), say("Since")], rows)],
        )
    ]


def _containers(body: dict[str, Any], *, live: bool = True) -> list[ViewBlock]:
    """A pod's containers with their states, or a template's without them:
    a template has no state, ready or restarts to show."""
    spec = as_dict(body.get("spec"))
    statuses = {
        str(as_dict(one).get("name")): as_dict(one)
        for one in as_list(as_dict(body.get("status")).get("containerStatuses"))
    }
    rows: list[list[ViewValue]] = []
    for container in as_list(spec.get("initContainers")) + as_list(spec.get("containers")):
        container = as_dict(container)
        name = str(container.get("name") or "")
        state = statuses.get(name, {})
        current = as_dict(state.get("state"))
        word = next(iter(current), "") if current else ""
        reason = as_dict(current.get(word)).get("reason") if word else None
        shown = str(reason or word or "—")
        ports = [
            f"{as_dict(port).get('containerPort')}/{as_dict(port).get('protocol', 'TCP')}"
            for port in as_list(container.get("ports"))
        ]
        state_cells: list[ViewValue] = [
            StateValue(word=shown, tone=tone_of("Running" if word == "running" else shown)),
            BooleanValue(value=bool(state.get("ready"))),
            NumberValue(value=float(state.get("restartCount") or 0)),
        ]
        rows.append(
            [
                text(name),
                code(str(container.get("image") or "")),
                *(state_cells if live else []),
                text(", ".join(ports)) if ports else EmptyValue(),
            ]
        )
    if not rows:
        return []
    columns = [say("Name"), say("Image")]
    if live:
        columns += [say("State"), say("Ready"), say("Restarts")]
    return [SectionBlock(title=say("Containers"), blocks=[table([*columns, say("Ports")], rows)])]


def _pod(body: dict[str, Any]) -> list[ViewBlock]:
    spec = as_dict(body.get("spec"))
    status = as_dict(body.get("status"))
    fields = [
        ViewField(label=say("Node"), value=word_value(spec.get("nodeName"))),
        ViewField(label=say("Pod IP"), value=word_value(status.get("podIP"))),
        ViewField(label=say("Host IP"), value=word_value(status.get("hostIP"))),
        ViewField(label=say("Started"), value=at_value(status.get("startTime"))),
        ViewField(label=say("Service account"), value=word_value(spec.get("serviceAccountName"))),
        ViewField(label=say("Restart policy"), value=word_value(spec.get("restartPolicy"))),
        ViewField(label=say("QoS class"), value=word_value(status.get("qosClass"))),
    ]
    return [FieldsBlock(fields=fields), *_containers(body)]


def _workload(resource: Resource, body: dict[str, Any]) -> list[ViewBlock]:
    spec = as_dict(body.get("spec"))
    status = as_dict(body.get("status"))
    fields: list[ViewField] = []
    if resource.key == "apps/daemonsets":
        fields += [
            ViewField(label=say("Desired"), value=NumberValue(value=float(status.get("desiredNumberScheduled") or 0))),
            ViewField(label=say("Ready"), value=NumberValue(value=float(status.get("numberReady") or 0))),
            ViewField(label=say("Up to date"), value=NumberValue(value=float(status.get("updatedNumberScheduled") or 0))),
        ]
    else:
        fields += [
            ViewField(label=say("Replicas wanted"), value=NumberValue(value=float(spec.get("replicas", 1) or 0))),
            ViewField(label=say("Ready"), value=NumberValue(value=float(status.get("readyReplicas") or 0))),
            ViewField(label=say("Up to date"), value=NumberValue(value=float(status.get("updatedReplicas") or 0))),
            ViewField(label=say("Available"), value=NumberValue(value=float(status.get("availableReplicas") or 0))),
        ]
    strategy = as_dict(spec.get("strategy") or spec.get("updateStrategy")).get("type")
    fields.append(ViewField(label=say("Strategy"), value=word_value(strategy)))
    selector = as_dict(as_dict(spec.get("selector")).get("matchLabels"))
    if selector:
        fields.append(ViewField(label=say("Selector"), value=chips([f"{k}={v}" for k, v in sorted(selector.items())])))
    template = {"spec": as_dict(as_dict(spec.get("template")).get("spec"))}
    return [FieldsBlock(fields=fields), *_containers(template, live=False)]


def _service(body: dict[str, Any]) -> list[ViewBlock]:
    spec = as_dict(body.get("spec"))
    ingress = as_list(as_dict(as_dict(body.get("status")).get("loadBalancer")).get("ingress"))
    external = [str(as_dict(one).get("ip") or as_dict(one).get("hostname") or "") for one in ingress]
    fields = [
        ViewField(label=say("Type"), value=word_value(spec.get("type"))),
        ViewField(label=say("Cluster IP"), value=word_value(spec.get("clusterIP"))),
        ViewField(label=say("External"), value=chips(external) if external else EmptyValue()),
        ViewField(
            label=say("Selector"),
            value=chips([f"{k}={v}" for k, v in sorted(as_dict(spec.get("selector")).items())])
            if spec.get("selector")
            else EmptyValue(),
        ),
    ]
    rows: list[list[ViewValue]] = [
        [
            word_value(as_dict(port).get("name")),
            text(str(as_dict(port).get("port"))),
            word_value(as_dict(port).get("targetPort")),
            word_value(as_dict(port).get("nodePort")),
            word_value(as_dict(port).get("protocol") or "TCP"),
        ]
        for port in as_list(spec.get("ports"))
    ]
    blocks: list[ViewBlock] = [FieldsBlock(fields=fields)]
    if rows:
        blocks.append(
            SectionBlock(
                title=say("Ports"),
                blocks=[table([say("Name"), say("Port"), say("Target"), say("Node port"), say("Protocol")], rows)],
            )
        )
    return blocks


def _node(body: dict[str, Any]) -> list[ViewBlock]:
    status = as_dict(body.get("status"))
    info = as_dict(status.get("nodeInfo"))
    capacity = as_dict(status.get("capacity"))
    allocatable = as_dict(status.get("allocatable"))
    fields = [
        ViewField(label=say("Kubelet"), value=word_value(info.get("kubeletVersion"))),
        ViewField(label=say("OS image"), value=word_value(info.get("osImage"))),
        ViewField(label=say("Kernel"), value=word_value(info.get("kernelVersion"))),
        ViewField(label=say("Container runtime"), value=word_value(info.get("containerRuntimeVersion"))),
        ViewField(label=say("Architecture"), value=word_value(info.get("architecture"))),
        ViewField(label=say("Unschedulable"), value=BooleanValue(value=bool(as_dict(body.get("spec")).get("unschedulable")))),
        ViewField(
            label=say("Addresses"),
            value=chips([f"{as_dict(one).get('type')}: {as_dict(one).get('address')}" for one in as_list(status.get("addresses"))]),
        ),
    ]
    rows: list[list[ViewValue]] = [
        [text(key), word_value(capacity.get(key)), word_value(allocatable.get(key))]
        for key in sorted(set(capacity) | set(allocatable))
    ]
    blocks: list[ViewBlock] = [FieldsBlock(fields=fields)]
    if rows:
        blocks.append(
            SectionBlock(
                title=say("Capacity"),
                blocks=[table([say("Resource"), say("Capacity"), say("Allocatable")], rows)],
            )
        )
    return blocks


def _claim(body: dict[str, Any]) -> list[ViewBlock]:
    spec = as_dict(body.get("spec"))
    status = as_dict(body.get("status"))
    return [
        FieldsBlock(
            fields=[
                ViewField(label=say("Storage class"), value=word_value(spec.get("storageClassName"))),
                ViewField(label=say("Requested"), value=word_value(as_dict(as_dict(spec.get("resources")).get("requests")).get("storage"))),
                ViewField(label=say("Capacity"), value=word_value(as_dict(status.get("capacity")).get("storage"))),
                ViewField(label=say("Access modes"), value=chips([str(one) for one in as_list(spec.get("accessModes"))])),
                ViewField(label=say("Volume"), value=word_value(spec.get("volumeName"))),
            ]
        )
    ]


def _secret(body: dict[str, Any]) -> list[ViewBlock]:
    data = as_dict(body.get("data"))
    rows: list[list[ViewValue]] = [
        [text(str(key)), BytesValue(value=_size_of(value))] for key, value in sorted(data.items())
    ]
    blocks: list[ViewBlock] = [
        FieldsBlock(fields=[ViewField(label=say("Type"), value=word_value(body.get("type")))]),
        NoticeBlock(text=say("A secret's values are not shown here; only its keys and their sizes")),
    ]
    if rows:
        blocks.append(SectionBlock(title=say("Keys"), blocks=[table([say("Key"), say("Size")], rows)]))
    return blocks


def _config_map(body: dict[str, Any]) -> list[ViewBlock]:
    data = as_dict(body.get("data"))
    found = [ViewPair(name=str(key), value=str(value)) for key, value in sorted(data.items())]
    binary = sorted(as_dict(body.get("binaryData")))
    blocks: list[ViewBlock] = []
    if found:
        blocks.append(SectionBlock(title=say("Data"), blocks=[pairs(found)]))
    if binary:
        blocks.append(FieldsBlock(fields=[ViewField(label=say("Binary keys"), value=chips(binary))]))
    return blocks


def _kind_blocks(resource: Resource, body: dict[str, Any]) -> list[ViewBlock]:
    key = resource.key
    if key == "/pods":
        return _pod(body)
    if key in ("apps/deployments", "apps/statefulsets", "apps/daemonsets", "apps/replicasets"):
        return _workload(resource, body)
    if key == "/services":
        return _service(body)
    if key == "/nodes":
        return _node(body)
    if key == "/persistentvolumeclaims":
        return _claim(body)
    if key == "/secrets":
        return _secret(body)
    if key == "/configmaps":
        return _config_map(body)
    return []


def object_view(resource: Resource, body: dict[str, Any]) -> DocumentView:
    metadata = as_dict(body.get("metadata"))
    name = str(metadata.get("name") or "")
    namespace = metadata.get("namespace")
    blocks: list[ViewBlock] = [
        _metadata_block(resource, body),
        *_kind_blocks(resource, body),
        *_conditions(body),
        *_labels_section(body),
    ]
    subtitle = text(resource.kind if not namespace else f"{resource.kind} · {namespace}")
    header = ViewHeader(title=name or resource.kind, subtitle=subtitle, state=state_of(resource, body))
    return DocumentView(header=header, blocks=blocks)


def editable_yaml(body: dict[str, Any]) -> str:
    """An object as `kubectl edit` opens it, `managedFields` and `status` left
    out: the cluster keeps the first itself and ignores the second on a write."""
    shown = copy.deepcopy(body)
    as_dict(shown.get("metadata")).pop("managedFields", None)
    shown.pop("status", None)
    return str(yaml.safe_dump(shown, sort_keys=False, allow_unicode=True, width=120))


def edited_object(text: str, resource: Resource, named: Any) -> dict[str, Any]:
    """The edited YAML read back, refused when it is no longer the same object."""
    try:
        edited = yaml.safe_load(text)
    except yaml.YAMLError:
        raise ValueError(say("This is not YAML the cluster could read")) from None
    if not isinstance(edited, dict) or not isinstance(edited.get("metadata"), dict):
        raise ValueError(say("Every object has apiVersion, kind and metadata"))
    group, _, _ = str(edited.get("apiVersion") or "").rpartition("/")
    metadata = edited["metadata"]
    same = (
        group == resource.group
        and edited.get("kind") == resource.kind
        and metadata.get("name") == named.name
        and (metadata.get("namespace") or None) == named.namespace
    )
    if not same:
        raise ValueError(
            say("Its kind, name and namespace stay as they were; New from YAML makes another object")
        )
    return edited
