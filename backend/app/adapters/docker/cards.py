"""An image's, a volume's and a network's inspect as a view (D422).

Each from its inspect and, where the inspect leaves them out, the containers
the catalog lists anyway (D407): who uses an image or mounts a volume is
counted from the containers, as the levels count it. A network's inspect names
its own.
"""

import re
from typing import Any

from app.adapters.docker.card import (
    as_dict,
    at_value,
    command_value,
    environment_pairs,
    labels_in,
    state_value,
    word_value,
)
from app.adapters.docker.catalog import image_title, leaf_id, tags_of, view_id
from app.adapters.docker.inventory import (
    name_of,
    state_of,
    users_of_image,
    users_of_volume,
)
from app.adapters.views import (
    BooleanValue,
    BytesValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    LinkValue,
    PairsBlock,
    SectionBlock,
    ViewField,
    ViewHeader,
    ViewPair,
    ViewValue,
    chips,
    code,
    pairs,
    table,
    text,
)
from app.core.translation import say

_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")


def image_view(inspect: dict[str, Any], containers: list[dict[str, Any]]) -> DocumentView:
    config = as_dict(inspect.get("Config"))
    image_id = str(inspect.get("Id") or "")
    size = inspect.get("Size")
    layers = as_dict(inspect.get("RootFS")).get("Layers") or []
    platform = "/".join(
        str(part) for part in (inspect.get("Os"), inspect.get("Architecture"), inspect.get("Variant")) if part
    )
    fields = [
        ViewField(label=say("Tags"), value=chips(tags_of(inspect)) if tags_of(inspect) else EmptyValue()),
        ViewField(label=say("ID"), value=code(image_id)),
        ViewField(
            label=say("Size"),
            value=BytesValue(value=size) if isinstance(size, int) and size >= 0 else EmptyValue(),
        ),
        ViewField(label=say("Created"), value=at_value(inspect.get("Created"))),
        ViewField(label=say("Platform"), value=word_value(platform)),
        ViewField(label=say("Entrypoint"), value=command_value(config.get("Entrypoint"))),
        ViewField(label=say("Command"), value=command_value(config.get("Cmd"))),
        ViewField(label=say("Working directory"), value=word_value(config.get("WorkingDir"))),
        ViewField(label=say("User"), value=word_value(config.get("User"))),
        ViewField(
            label=say("Exposed ports"),
            value=chips(sorted(as_dict(config.get("ExposedPorts"))))
            if config.get("ExposedPorts")
            else EmptyValue(),
        ),
        ViewField(
            label=say("Layers"),
            # The layers themselves are the History table (D408).
            value=LinkValue(
                text=say("{count} layers", count=len(layers)),
                node_id=view_id("image", image_id, "history"),
            )
            if image_id
            else EmptyValue(),
        ),
    ]
    users = users_of_image(containers, image_id)
    return DocumentView(
        header=ViewHeader(
            title=image_title(inspect),
            subtitle=None if not platform else text(platform),
        ),
        blocks=[
            SectionBlock(title=say("Overview"), blocks=[FieldsBlock(fields=fields)]),
            SectionBlock(
                title=say("Containers"),
                blocks=[
                    table(
                        [say("Container"), say("State")],
                        [[_container(one), state_value(state_of(one))] for one in users],
                    )
                ],
            ),
            SectionBlock(title=say("Environment"), blocks=[environment_pairs(config)]),
            _labels_section(labels_in(config)),
        ],
    )


def volume_view(inspect: dict[str, Any], containers: list[dict[str, Any]]) -> DocumentView:
    name = str(inspect.get("Name") or "")
    fields = [
        ViewField(label=say("Driver"), value=word_value(inspect.get("Driver"))),
        ViewField(label=say("Mount point"), value=_code_or_empty(inspect.get("Mountpoint"))),
        ViewField(label=say("Scope"), value=word_value(inspect.get("Scope"))),
        ViewField(label=say("Created"), value=at_value(inspect.get("CreatedAt"))),
    ]
    rows: list[list[ViewValue]] = []
    for one in users_of_volume(containers, name):
        for mount in one.get("Mounts") or []:
            if isinstance(mount, dict) and mount.get("Type") == "volume" and mount.get("Name") == name:
                rows.append(
                    [
                        _container(one),
                        state_value(state_of(one)),
                        _code_or_empty(mount.get("Destination")),
                        BooleanValue(value=mount.get("RW") is not False),
                    ]
                )
    return DocumentView(
        header=ViewHeader(title=name or "?", subtitle=word_value(inspect.get("Driver"))),
        blocks=[
            SectionBlock(title=say("Overview"), blocks=[FieldsBlock(fields=fields)]),
            SectionBlock(
                title=say("Containers"),
                blocks=[
                    table([say("Container"), say("State"), say("Destination"), say("Writable")], rows)
                ],
            ),
            SectionBlock(title=say("Options"), blocks=[_pairs(inspect.get("Options"))]),
            _labels_section(labels_in(inspect)),
        ],
    )


def network_view(inspect: dict[str, Any]) -> DocumentView:
    ipam = as_dict(inspect.get("IPAM"))
    fields = [
        ViewField(label=say("ID"), value=code(str(inspect.get("Id") or ""))),
        ViewField(label=say("Driver"), value=word_value(inspect.get("Driver"))),
        ViewField(label=say("Scope"), value=word_value(inspect.get("Scope"))),
        ViewField(label=say("Internal"), value=BooleanValue(value=inspect.get("Internal") is True)),
        ViewField(label=say("Attachable"), value=BooleanValue(value=inspect.get("Attachable") is True)),
        ViewField(label=say("IPv6"), value=BooleanValue(value=inspect.get("EnableIPv6") is True)),
        ViewField(label=say("Created"), value=at_value(inspect.get("Created"))),
    ]
    subnets: list[list[ViewValue]] = [
        [
            word_value(entry.get("Subnet")),
            word_value(entry.get("Gateway")),
            word_value(entry.get("IPRange")),
        ]
        for entry in ipam.get("Config") or []
        if isinstance(entry, dict)
    ]
    attached: list[list[ViewValue]] = []
    for key, endpoint in sorted(
        as_dict(inspect.get("Containers")).items(),
        key=lambda item: str(as_dict(item[1]).get("Name") or ""),
    ):
        endpoint = as_dict(endpoint)
        named = str(endpoint.get("Name") or key[:12])
        attached.append(
            [
                LinkValue(text=named, node_id=leaf_id("container", key))
                if _CONTAINER_ID.match(key)
                else text(named),
                word_value(endpoint.get("IPv4Address")),
                word_value(endpoint.get("IPv6Address")),
                word_value(endpoint.get("MacAddress")),
            ]
        )
    return DocumentView(
        header=ViewHeader(
            title=str(inspect.get("Name") or "?"), subtitle=word_value(inspect.get("Driver"))
        ),
        blocks=[
            SectionBlock(title=say("Overview"), blocks=[FieldsBlock(fields=fields)]),
            SectionBlock(
                title=say("Addresses"),
                blocks=[table([say("Subnet"), say("Gateway"), say("IP range")], subnets)],
            ),
            SectionBlock(
                title=say("Containers"),
                blocks=[
                    table(
                        [say("Container"), say("IPv4 address"), say("IPv6 address"), say("MAC address")],
                        attached,
                    )
                ],
            ),
            SectionBlock(title=say("Options"), collapsed=True, blocks=[_pairs(inspect.get("Options"))]),
            _labels_section(labels_in(inspect)),
        ],
    )


def _container(listed: dict[str, Any]) -> ViewValue:
    key = str(listed.get("Id") or "")
    named = name_of(listed)
    return LinkValue(text=named, node_id=leaf_id("container", key)) if _CONTAINER_ID.match(key) else text(named)


def _labels_section(labels: dict[str, str]) -> SectionBlock:
    return SectionBlock(
        title=say("Labels"),
        collapsed=True,
        blocks=[pairs([ViewPair(name=k, value=v) for k, v in sorted(labels.items())])],
    )


def _pairs(value: Any) -> PairsBlock:
    found = as_dict(value)
    return pairs([ViewPair(name=str(k), value=str(v)) for k, v in sorted(found.items())])


def _code_or_empty(value: Any) -> ViewValue:
    return code(value) if isinstance(value, str) and value else EmptyValue()
