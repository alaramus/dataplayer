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
    Generated,
    ServiceTemplate,
    Value,
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
    # The port on the host, when the service is published there at all. None
    # means the container is reachable only from the network above.
    published_port: int | None = None


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
    published_port: int | None
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


def settle_credentials(template: ServiceTemplate) -> Credentials:
    """What this service's credentials are: the constants, and a new secret.

    Called once per service. Calling it twice gives two different passwords,
    which is why the plan carries the answer rather than a way of asking again.
    """
    settled: dict[CredentialSlot, str] = {}
    for slot, source in template.credentials.items():
        settled[slot] = (
            source.value if isinstance(source, Fixed) else generate_password()
        )
    return settled


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
) -> ServicePlan:
    """What would be created for one service of this kind.

    The credentials are settled here rather than passed in, so there is one
    moment at which a service's password comes into existence.
    """
    credentials = settle_credentials(template)
    return ServicePlan(
        service_id=service_id,
        template=template,
        credentials=credentials,
        container=build_container(
            template,
            service_id=service_id,
            owner_id=owner_id,
            credentials=credentials,
            placement=placement,
        ),
    )


def build_container(
    template: ServiceTemplate,
    *,
    service_id: UUID,
    owner_id: UUID,
    credentials: Credentials,
    placement: Placement,
) -> ContainerSpec:
    return ContainerSpec(
        name=container_name(service_id, template),
        image=template.image,
        environment={
            key: _credential_value(value, credentials)
            for key, value in template.environment.items()
        },
        command=tuple(
            _credential_value(part, credentials) for part in template.command
        ),
        volume=volume_name(service_id, template),
        data_path=template.data_path,
        container_port=template.container_port,
        published_port=placement.published_port,
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
        for field, value in plan.template.connector_options.items()
    }


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
