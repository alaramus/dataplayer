"""Everything that would be created for one service, settled before it runs.

Pure: nothing here talks to Docker, and the same inputs give the same plan.
That is what makes "no arbitrary image, command, environment key, volume or
host path comes from the client" a thing a test can hold, rather than a claim
about a code path that only runs when a daemon is listening.

Secrets pass through here, so nothing in this module has a readable `repr`
that would carry one into a log.
"""

import secrets
import string
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.services.templates import (
    CredentialSlot,
    CredentialValue,
    Fixed,
    FromKey,
    Generated,
    ServiceTemplate,
    Shape,
    Value,
    shape_of,
    slots_of,
)

# Letters and digits only. A generated password is never typed by a person and
# never parsed by anything but a driver, so the alphabet is chosen to survive
# every place it will be written — an environment variable, a connection
# string, a YAML file somebody pastes — rather than to look strong.
# 32 characters of it is about 190 bits.
PASSWORD_ALPHABET = string.ascii_letters + string.digits
PASSWORD_LENGTH = 32

# What marks a container as this application's. Names are for people to read
# and can be changed; a label is what a later sweep for orphans matches on.
SERVICE_LABEL = "dataplayer.service"
TEMPLATE_LABEL = "dataplayer.template"
OWNER_LABEL = "dataplayer.owner"
# What a container that is a program rather than a service is marked
# with. It lives and dies inside one job, so it never appears in a sweep
# for orphans — but a person reading `docker ps` mid-backup should still
# be able to tell what it is.
TOOL_LABEL = "dataplayer.tool"

# Both names begin with this, so everything one installation made can be seen
# at a glance in `docker ps` — the labels are what code matches on.
NAME_PREFIX = "dataplayer-svc"

# How much of the service id goes into a name. Enough that two services cannot
# collide in practice, short enough that a person can read the name.
NAME_ID_LENGTH = 12

# What credentials are, once settled: a value per slot the template named.
Credentials = Mapping[CredentialSlot, str]


@dataclass(frozen=True)
class Placement:
    """Where a service is put, decided by the server when it is placed.

    Separate from the template because it is not a property of the kind of
    service: the same PostgreSQL template placed twice is two containers on
    two ports.
    """

    # The Docker network the container joins, when there is one to join. The
    # application reaches a service by container name on a shared network;
    # without one, only a published port is left.
    network: str | None = None
    # Whether the service is also reachable from the machine this server runs
    # on. Bound to the loopback wherever it is honoured (D86).
    publish: bool = False
    # Which port on the host, when somebody asked for a particular one.
    # `None` means the runtime picks a free one, which is what it does for
    # everybody who has no reason to care: this application would otherwise
    # have to bind a socket to find out what is free and then race whoever
    # took it in between. A number here is a person saying they will point
    # something at it that already knows the port.
    host_port: int | None = None


@dataclass(frozen=True)
class Endpoint:
    """Where a running service is reached from, as a connector would say it."""

    host: str
    port: int


@dataclass(frozen=True)
class ContainerSpec:
    """The exact container that would be created, and nothing else.

    Every field is either a constant from the template or something the server
    decided. There is no field for a client to fill, which is the whole point:
    what runs is not a function of a request.
    """

    name: str
    image: str
    environment: Mapping[str, str]
    command: tuple[str, ...]
    # One named volume per service, mounted where the image keeps its data.
    # Named rather than bound to a host path: a bind mount needs a path on the
    # host, and a path on the host is the thing no part of this may choose.
    volume: str
    data_path: str
    container_port: int
    # Whether to ask the runtime for a port on the host, and which one when
    # somebody named it. Without a number the runtime picks, and what it
    # picked is read off the container afterwards.
    publish: bool
    host_port: int | None
    network: str | None
    labels: Mapping[str, str]

    def __repr__(self) -> str:
        """Enough to identify it, and none of the environment's values.

        The environment holds the password the service was made with. A
        dataclass would print it, and one traceback with a spec in a local
        variable would put it in a log for good.
        """
        keys = ", ".join(sorted(self.environment))
        return (
            f"ContainerSpec(name={self.name!r}, image={self.image!r}, "
            f"environment keys: {keys})"
        )


@dataclass(frozen=True)
class ServicePlan:
    """One service, fully decided: what runs and what it was given.

    The credentials are kept beside the container rather than read back out of
    it later, because the connector this becomes needs the same values the
    container was started with — the old application read them from two places
    and could save a connector that did not match its own container.
    """

    service_id: UUID
    template: ServiceTemplate
    # Which of the template's shapes this service took: with a password, or
    # without one where the template allows that. Carried rather than worked
    # out again, because the connector must be described the same way the
    # container was started.
    shape: Shape
    credentials: Credentials
    container: ContainerSpec

    def __repr__(self) -> str:
        return (
            f"ServicePlan(service_id={self.service_id!r}, "
            f"template={self.template.key!r})"
        )


def generate_password() -> str:
    """A password for one service, from the system's own source of randomness."""
    return "".join(
        secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH)
    )


def settle_credentials(
    template: ServiceTemplate,
    chosen: Mapping[CredentialSlot, str] | None = None,
    *,
    shape: Shape | None = None,
) -> Credentials:
    """What this service's credentials are: the constants, and a new secret.

    Called once per service. Calling it twice gives two different passwords,
    which is why the plan carries the answer rather than a way of asking again.

    A requester may name the slots the template calls choosable, and nothing
    else: a value offered for a slot the template did not open is ignored here
    and refused before it ever gets here.

    Only the slots the shape refers to are settled. A Redis asked to run
    without a password names none, so no secret comes into existence for it —
    rather than one being made and then left out of the container, which is
    the version of this that leaves a password in a log.

    What is read off a key comes in with `chosen`, looked up by whoever holds
    the store of keys; a shape that needs it and was not given it is refused.
    """
    named = chosen or {}
    used = slots_of(shape if shape is not None else shape_of(template, protected=True))
    settled: dict[CredentialSlot, str] = {}
    for slot, source in template.credentials.items():
        if slot not in used:
            continue
        if isinstance(source, FromKey):
            if slot not in named:
                raise ValueError(f"{template.key} was given no key to sign in with")
            settled[slot] = named[slot]
            continue
        if slot in template.choosable and slot in named:
            settled[slot] = named[slot]
            continue
        settled[slot] = (
            source.value if isinstance(source, Fixed) else generate_password()
        )
    return settled


def settled_names(
    template: ServiceTemplate, chosen: Mapping[str, str] | None = None
) -> dict[CredentialSlot, str]:
    """The credentials of a service that are not secrets, without settling any.

    What a service calls its role and its database: a constant of the template
    unless the requester named something else. Deliberately not
    `settle_credentials` with the secret thrown away — that one makes a
    password every time it is called, and a function called to fill a screen
    must not be one that creates secrets.
    """
    named = chosen or {}
    return {
        slot: named.get(slot, source.value)
        for slot, source in template.credentials.items()
        if isinstance(source, Fixed)
    }


def container_name(service_id: UUID, template: ServiceTemplate) -> str:
    return f"{NAME_PREFIX}-{template.key}-{service_id.hex[:NAME_ID_LENGTH]}"


def volume_name(service_id: UUID, template: ServiceTemplate) -> str:
    return f"{container_name(service_id, template)}-data"


def build_plan(
    template: ServiceTemplate,
    *,
    service_id: UUID,
    owner_id: UUID,
    placement: Placement,
    chosen: Mapping[CredentialSlot, str] | None = None,
    protected: bool = True,
    keyed: bool = False,
) -> ServicePlan:
    """What would be created for one service of this kind.

    The credentials are settled here rather than passed in, so there is one
    moment at which a service's password comes into existence — and one place
    where a password somebody chose is used instead of one being made up.
    """
    shape = shape_of(template, protected=protected, keyed=keyed)
    credentials = settle_credentials(template, chosen, shape=shape)
    return ServicePlan(
        service_id=service_id,
        template=template,
        shape=shape,
        credentials=credentials,
        container=build_container(
            template,
            service_id=service_id,
            owner_id=owner_id,
            credentials=credentials,
            placement=placement,
            shape=shape,
        ),
    )


def build_container(
    template: ServiceTemplate,
    *,
    service_id: UUID,
    owner_id: UUID,
    credentials: Credentials,
    placement: Placement,
    shape: Shape | None = None,
) -> ContainerSpec:
    taken = shape if shape is not None else shape_of(template, protected=True)
    return ContainerSpec(
        name=container_name(service_id, template),
        image=template.image,
        environment={
            key: _credential_value(value, credentials)
            for key, value in taken.environment.items()
        },
        command=tuple(_credential_value(part, credentials) for part in taken.command),
        volume=volume_name(service_id, template),
        data_path=template.data_path,
        container_port=template.container_port,
        publish=placement.publish,
        host_port=placement.host_port if placement.publish else None,
        network=placement.network,
        labels={
            SERVICE_LABEL: str(service_id),
            TEMPLATE_LABEL: template.key,
            OWNER_LABEL: str(owner_id),
        },
    )


def connector_options(plan: ServicePlan, endpoint: Endpoint) -> dict[str, str | int]:
    """The options of the connector this service becomes.

    Field names and constants come from the template; the values come from
    what was settled and where the service ended up. The result is handed to
    the adapter's own options model, so a connector made this way is validated
    exactly as one somebody typed — and a template naming a field that model
    does not have is refused there rather than stored.
    """
    return {
        field: _value(value, plan.credentials, endpoint)
        for field, value in plan.shape.connector_options.items()
    }


def described_options(
    shape: Shape, known: Mapping[CredentialSlot, str], endpoint: Endpoint
) -> dict[str, str | int]:
    """The connector's options as far as they are known, at another address.

    For saying where a service listens rather than for connecting: the fields
    are the adapter's own, so the source type writes its address from them as
    it would from its form (D89), and a credential that is not known — the
    password, unless it is being handed over — is simply absent.
    """
    found: dict[str, str | int] = {}
    for field, value in shape.connector_options.items():
        if isinstance(value, Fixed):
            found[field] = value.value
        elif value == "host":
            found[field] = endpoint.host
        elif value == "port":
            found[field] = endpoint.port
        elif value in known:
            found[field] = known[value]
    return found


def _credential_value(value: CredentialValue, credentials: Credentials) -> str:
    if isinstance(value, Fixed):
        return value.value
    return credentials[value]


def _value(
    value: Value, credentials: Credentials, endpoint: Endpoint
) -> str | int:
    if isinstance(value, Fixed):
        return value.value
    if value == "host":
        return endpoint.host
    if value == "port":
        return endpoint.port
    return credentials[value]


def is_generated(template: ServiceTemplate, slot: CredentialSlot) -> bool:
    return isinstance(template.credentials.get(slot), Generated)
