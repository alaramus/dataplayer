"""A container's inspect as a view of its document (D422, D419–D421).

Built from the inspect the source already reads for the tree; nothing else is
asked of the daemon. A plain function of that document, so a recorded inspect
is enough to test it. The values every Docker view reads the same way are
here too; `cards.py` holds the image's, the volume's and the network's.
"""

from typing import Any

from app.adapters.catalog import ContainerState
from app.adapters.docker.catalog import image_title, leaf_id, project_id
from app.adapters.docker.inventory import (
    COMPOSE_PROJECT,
    COMPOSE_SERVICE,
    datetime_of,
    instant,
)
from app.adapters.views import (
    BooleanValue,
    BytesValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    LinkValue,
    NoticeBlock,
    NumberValue,
    PairsBlock,
    SectionBlock,
    StateValue,
    Tone,
    ViewBlock,
    ViewField,
    ViewHeader,
    ViewPair,
    ViewValue,
    code,
    moment,
    pairs,
    table,
    text,
)
from app.core.translation import N_, say

# A name that says its value is a secret; the value cannot be judged (D421).
_SENSITIVE = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "KEY", "CREDENTIAL", "PRIVATE")

# More restarts than this are worth a sentence (D422).
_RESTARTS_TOLD = 3

_WORDS: dict[ContainerState, str] = {
    "running": N_("running"),
    "healthy": N_("healthy"),
    "unhealthy": N_("unhealthy"),
    "starting": N_("starting"),
    "paused": N_("paused"),
    "restarting": N_("restarting"),
    "stopped": N_("stopped"),
    "failed": N_("failed"),
    "created": N_("never started"),
    "removing": N_("removing"),
    "dead": N_("dead"),
    "unknown": N_("unknown"),
}
_TONES: dict[ContainerState, Tone] = {
    "running": "good",
    "healthy": "good",
    "starting": "busy",
    "restarting": "busy",
    "removing": "busy",
    "unhealthy": "bad",
    "failed": "bad",
    "dead": "bad",
    "paused": "warning",
    "stopped": "neutral",
    "created": "neutral",
    "unknown": "neutral",
}
_HEALTH_TONES: dict[str, Tone] = {"healthy": "good", "starting": "busy", "unhealthy": "bad"}
_HEALTH_WORDS = {
    "healthy": N_("healthy"),
    "starting": N_("starting"),
    "unhealthy": N_("unhealthy"),
    "none": N_("none"),
}


def state_value(state: ContainerState) -> StateValue:
    """The state word of D407 and its tone (D422)."""
    return StateValue(word=say(_WORDS[state]), tone=_TONES[state])


def is_sensitive(name: str) -> bool:
    folded = name.upper()
    return any(word in folded for word in _SENSITIVE)


def inspected_state(inspect: dict[str, Any]) -> ContainerState:
    """The state word of D407, read from inspect rather than from the list."""
    state = as_dict(inspect.get("State"))
    status = str(state.get("Status") or "")
    if status == "running":
        health = str(as_dict(state.get("Health")).get("Status") or "")
        if health in ("healthy", "unhealthy", "starting"):
            return health  # type: ignore[return-value] # narrowed by the tuple above
        return "running"
    if status == "exited":
        return "stopped" if state.get("ExitCode") in (0, None) else "failed"
    if status in ("paused", "restarting", "created", "removing", "dead"):
        return status  # type: ignore[return-value] # narrowed by the tuple above
    return "unknown"


def container_view(inspect: dict[str, Any]) -> DocumentView:
    state = as_dict(inspect.get("State"))
    config = as_dict(inspect.get("Config"))
    host = as_dict(inspect.get("HostConfig"))
    word = inspected_state(inspect)
    blocks: list[ViewBlock] = [*_notices(inspect, state), _overview(inspect, state, config, host)]
    health = _health(config, state)
    if health is not None:
        blocks.append(health)
    blocks += [
        _network(inspect, host),
        _storage(inspect),
        SectionBlock(title=say("Environment"), blocks=[environment_pairs(config)]),
        SectionBlock(
            title=say("Labels"),
            collapsed=True,
            blocks=[pairs([ViewPair(name=k, value=v) for k, v in sorted(labels_in(config).items())])],
        ),
        _resources(host),
    ]
    return DocumentView(
        header=ViewHeader(
            title=str(inspect.get("Name") or "").lstrip("/") or str(inspect.get("Id", ""))[:12],
            subtitle=_image(inspect, config),
            state=state_value(word),
        ),
        blocks=blocks,
    )


def _notices(inspect: dict[str, Any], state: dict[str, Any]) -> list[ViewBlock]:
    found: list[ViewBlock] = []
    if state.get("OOMKilled") is True:
        found.append(NoticeBlock(text=say("It was killed for running out of memory"), tone="bad"))
    restarts = inspect.get("RestartCount")
    if isinstance(restarts, int) and restarts > _RESTARTS_TOLD:
        found.append(
            NoticeBlock(
                text=say("This container restarted {count} times", count=restarts),
                tone="warning",
            )
        )
    return found


def _overview(
    inspect: dict[str, Any],
    state: dict[str, Any],
    config: dict[str, Any],
    host: dict[str, Any],
) -> SectionBlock:
    running = state.get("Running") is True
    fields = [
        ViewField(label=say("ID"), value=code(str(inspect.get("Id", "")))),
        ViewField(label=say("Created"), value=at_value(inspect.get("Created"))),
    ]
    if running:
        fields.append(ViewField(label=say("Started"), value=at_value(state.get("StartedAt"))))
    else:
        fields.append(ViewField(label=say("Finished"), value=at_value(state.get("FinishedAt"))))
        exit_code = state.get("ExitCode")
        fields.append(
            ViewField(
                label=say("Exit code"),
                value=NumberValue(value=exit_code)
                if isinstance(exit_code, int) and not isinstance(exit_code, bool)
                else EmptyValue(),
            )
        )
    policy = as_dict(host.get("RestartPolicy"))
    fields += [
        ViewField(label=say("Restart policy"), value=word_value(policy.get("Name"))),
        ViewField(label=say("Restarts"), value=count_value(inspect.get("RestartCount"))),
        ViewField(label=say("Command"), value=command_value(config.get("Cmd"))),
        ViewField(label=say("Entrypoint"), value=command_value(config.get("Entrypoint"))),
        ViewField(label=say("Working directory"), value=word_value(config.get("WorkingDir"))),
        ViewField(label=say("User"), value=word_value(config.get("User"))),
    ]
    labels = labels_in(config)
    project = labels.get(COMPOSE_PROJECT)
    if project:
        fields.append(
            ViewField(
                label=say("Compose project"),
                value=LinkValue(text=project, node_id=project_id(project)),
            )
        )
        fields.append(ViewField(label=say("Compose service"), value=word_value(labels.get(COMPOSE_SERVICE))))
    return SectionBlock(title=say("Overview"), blocks=[FieldsBlock(fields=fields)])


def _health(config: dict[str, Any], state: dict[str, Any]) -> SectionBlock | None:
    check = as_dict(config.get("Healthcheck"))
    tests = check.get("Test")
    # `["NONE"]` switches off a check the image declared.
    defined = isinstance(tests, list) and bool(tests) and tests[0] != "NONE"
    health = as_dict(state.get("Health"))
    if not defined and not health:
        return None
    status = str(health.get("Status") or "none")
    fields = [
        ViewField(
            label=say("Status"),
            value=StateValue(
                word=say(_HEALTH_WORDS[status if status in _HEALTH_WORDS else "none"]),
                tone=_HEALTH_TONES.get(status, "neutral"),
            ),
        ),
        ViewField(label=say("Failing streak"), value=count_value(health.get("FailingStreak"))),
    ]
    if isinstance(tests, list) and defined:
        # The first word says how the rest runs, not what runs.
        command = tests[1:] if tests[0] in ("CMD", "CMD-SHELL") else tests
        fields.append(ViewField(label=say("Check"), value=command_value(command)))
    rows: list[list[ViewValue]] = [
        [
            at_value(entry.get("Start")),
            NumberValue(value=entry["ExitCode"]) if isinstance(entry.get("ExitCode"), int) else EmptyValue(),
            code(str(entry.get("Output") or "").strip()),
        ]
        for entry in reversed(health.get("Log") or [])
        if isinstance(entry, dict)
    ]
    return SectionBlock(
        title=say("Health"),
        blocks=[
            FieldsBlock(fields=fields),
            table([say("Started"), say("Exit code"), say("Output")], rows),
        ],
    )


def _network(inspect: dict[str, Any], host: dict[str, Any]) -> SectionBlock:
    settings = as_dict(inspect.get("NetworkSettings"))
    ports: list[list[ViewValue]] = []
    for port, bindings in sorted(as_dict(settings.get("Ports")).items()):
        if not isinstance(bindings, list) or not bindings:
            ports.append([text(port), EmptyValue(), EmptyValue()])
            continue
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            host_port = str(binding.get("HostPort") or "")
            ports.append(
                [
                    text(port),
                    word_value(binding.get("HostIp")),
                    # An identifier, not a quantity: 8080, never "8,080".
                    text(host_port) if host_port else EmptyValue(),
                ]
            )
    networks: list[list[ViewValue]] = []
    for name, endpoint in sorted(as_dict(settings.get("Networks")).items()):
        endpoint = as_dict(endpoint)
        network_id = str(endpoint.get("NetworkID") or "")
        networks.append(
            [
                LinkValue(text=name, node_id=leaf_id("network", network_id))
                if len(network_id) == 64
                else text(name),
                word_value(endpoint.get("IPAddress")),
                word_value(endpoint.get("Gateway")),
            ]
        )
    return SectionBlock(
        title=say("Network"),
        blocks=[
            FieldsBlock(fields=[ViewField(label=say("Network mode"), value=word_value(host.get("NetworkMode")))]),
            table([say("Container port"), say("Host address"), say("Host port")], ports),
            table([say("Network"), say("Address"), say("Gateway")], networks),
        ],
    )


def _storage(inspect: dict[str, Any]) -> SectionBlock:
    rows: list[list[ViewValue]] = []
    for mount in inspect.get("Mounts") or []:
        if not isinstance(mount, dict):
            continue
        kind = str(mount.get("Type") or "")
        name = str(mount.get("Name") or "")
        source: ViewValue = (
            LinkValue(text=name, node_id=leaf_id("volume", name))
            if kind == "volume" and name
            else code(str(mount.get("Source") or ""))
            if mount.get("Source")
            else EmptyValue()
        )
        rows.append(
            [
                word_value(kind),
                source,
                code(str(mount.get("Destination") or "")),
                BooleanValue(value=mount.get("RW") is not False),
            ]
        )
    return SectionBlock(
        title=say("Storage"),
        blocks=[table([say("Type"), say("Source"), say("Destination"), say("Writable")], rows)],
    )


def environment_pairs(config: dict[str, Any]) -> PairsBlock:
    found: list[ViewPair] = []
    for entry in config.get("Env") or []:
        if not isinstance(entry, str):
            continue
        name, _, value = entry.partition("=")
        found.append(ViewPair(name=name, value=value, sensitive=is_sensitive(name)))
    return pairs(found)


def _resources(host: dict[str, Any]) -> SectionBlock:
    # Zero is how the daemon says "unlimited".
    memory = _positive(host.get("Memory"))
    cpus = _positive(host.get("NanoCpus"))
    pids = _positive(host.get("PidsLimit"))
    fields = [
        ViewField(
            label=say("Memory limit"),
            value=EmptyValue() if memory is None else BytesValue(value=memory),
        ),
        ViewField(
            label=say("CPU limit"),
            value=EmptyValue() if cpus is None else NumberValue(value=cpus / 1e9, unit=say("CPUs")),
        ),
        ViewField(
            label=say("Process limit"),
            value=EmptyValue() if pids is None else NumberValue(value=pids),
        ),
    ]
    return SectionBlock(title=say("Resources"), blocks=[FieldsBlock(fields=fields)])


def _image(inspect: dict[str, Any], config: dict[str, Any]) -> ViewValue:
    image_id = str(inspect.get("Image") or "")
    named = str(config.get("Image") or "") or image_title({"Id": image_id})
    if image_id.startswith("sha256:") and len(image_id) == 71:
        return LinkValue(text=named, node_id=leaf_id("image", image_id))
    return text(named) if named else EmptyValue()


def at_value(value: Any) -> ViewValue:
    return moment(datetime_of(instant(value)))


def word_value(value: Any) -> ViewValue:
    return text(str(value)) if isinstance(value, str) and value else EmptyValue()


def count_value(value: Any) -> ViewValue:
    if isinstance(value, int) and not isinstance(value, bool):
        return NumberValue(value=value)
    return EmptyValue()


def command_value(value: Any) -> ViewValue:
    if isinstance(value, list) and value:
        return code(" ".join(_quoted(str(part)) for part in value))
    if isinstance(value, str) and value:
        return code(value)
    return EmptyValue()


def _quoted(part: str) -> str:
    # Shown as a person would type it, so a part with a space stays one.
    return part if part and not any(c.isspace() or c in "\"'" for c in part) else repr(part)


def labels_in(config: dict[str, Any]) -> dict[str, str]:
    labels = config.get("Labels")
    return {str(k): str(v) for k, v in labels.items()} if isinstance(labels, dict) else {}


def _positive(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
