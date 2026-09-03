"""What this server may start, written here and chosen only by name.

The old application built a Docker service out of whatever the connector form
sent. `options.docker` could carry the image, the command, the port, the path
inside the container and even a path on the host to mount a rendered
configuration file from, and the whole thing was interpolated into a Mako
template and then into a `docker compose` command line built with an f-string.
A client that could name an image could run anything on the machine.

Here a client names a key from a closed registry and nothing else. Everything
that would be created — the image, the command, every environment key, the
volume, the port inside the container — is in this file, and the only values
that are not are the ones the server itself makes up (D80).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, get_args

# What may stand where a value is expected, in two kinds. A credential belongs
# to one service and is settled before it starts; a placement is settled when
# the service is put somewhere. A client supplies neither.
#
# Two types rather than one so that the environment of a container cannot ask
# for a port that nothing has assigned yet: what may appear where is a
# question mypy answers, not one a build-time check has to.
CredentialSlot = Literal["user", "password", "database"]
PlacementSlot = Literal["host", "port"]
Slot = CredentialSlot | PlacementSlot

USER: CredentialSlot = "user"
PASSWORD: CredentialSlot = "password"
DATABASE: CredentialSlot = "database"
HOST: PlacementSlot = "host"
PORT: PlacementSlot = "port"

CREDENTIAL_SLOTS: tuple[CredentialSlot, ...] = get_args(CredentialSlot)


@dataclass(frozen=True)
class Fixed:
    """A value written in this file rather than made up for one service.

    A wrapper rather than a bare string so that a constant which happens to
    read like a slot — a template whose database is literally called
    "database" — cannot be mistaken for one.
    """

    value: str


@dataclass(frozen=True)
class Generated:
    """A secret this server makes up, once, for one service.

    It carries nothing. How a secret is made is one rule and lives with the
    code that makes it; a template that could choose its own alphabet would be
    a template that could choose a weak one.
    """


# Either the name of something decided for this service, or a constant.
# Split the same way the slots are: an environment value cannot name a
# placement, and the compiler is what says so.
CredentialValue = CredentialSlot | Fixed
Value = Slot | Fixed


class UnknownServiceTemplate(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown service template: {key}")
        self.key = key


@dataclass(frozen=True)
class ServiceTemplate:
    """One approved service: what runs, and what the connector to it becomes.

    Both halves are here on purpose. A template whose container was described
    in one place and whose credentials were described in another is how the
    old application could start a container with one password and save a
    connector holding another.
    """

    key: str
    title: str
    description: str
    # Pinned to a version rather than to `latest`: a template is a statement
    # about what will run, and `latest` is a statement about whatever happens
    # to be published on the day somebody presses the button.
    image: str
    # The port the image itself listens on. What it is published as on the
    # host is decided when the service is placed, never here and never by a
    # client.
    container_port: int
    # Where the image keeps its data, and therefore where this service's one
    # named volume is mounted. No path on the host is ever named: a bind mount
    # is how the old application let a client reach the file system.
    data_path: str
    # How each credential slot is settled: written here, or made up per
    # service. Every slot a template uses must appear, which is what keeps one
    # constant from being written twice and drifting.
    credentials: Mapping[CredentialSlot, Fixed | Generated]
    # Which of those a requester may name instead, when they want to. A
    # closed set per template, so a request naming anything else is refused
    # rather than quietly ignored — and never `password`: a chosen password
    # would have to be written down somewhere between the request and the job
    # that uses it, and the only encrypted home for a service's password is
    # the connector it becomes (D4, D84).
    choosable: frozenset[CredentialSlot]
    # Every environment key the container gets, and where each value comes
    # from. A key that is not here is not passed.
    environment: Mapping[str, CredentialValue]
    # What the container is started with, when the image needs more than its
    # own entrypoint. Written as values rather than plain strings because one
    # image takes its password on the command line: `redis-server
    # --requirepass …` is how that image is told, and a template that could
    # only write constants there could not describe it.
    command: tuple[CredentialValue, ...]
    # The source type a ready service becomes, and how its options are filled.
    # The names are the fields of that adapter's own options model, so a
    # connector made from a service goes through the same schema as one
    # somebody typed.
    adapter_type: str
    connector_options: Mapping[str, Value]
    # How long this kind of service may reasonably take to become usable, in
    # seconds. Read by whatever waits for it, never by a client.
    startup_timeout_seconds: int


POSTGRES = ServiceTemplate(
    key="postgres",
    title="PostgreSQL",
    description=(
        "A PostgreSQL server of its own, started on this machine with "
        "credentials nobody has to choose."
    ),
    # The version this project runs itself, so a service made here behaves the
    # way the application's own database does.
    image="postgres:18",
    container_port=5432,
    # The image's own default, and the reason it is stated: the volume must be
    # mounted where the server writes, and that is the image's business rather
    # than a guess.
    data_path="/var/lib/postgresql",
    credentials={
        # Neither of these is a secret and neither is interesting to choose,
        # so both are written where they can be read.
        USER: Fixed("dataplayer"),
        DATABASE: Fixed("dataplayer"),
        PASSWORD: Generated(),
    },
    # The role and the database are names in somebody's own server, so they
    # are theirs to choose when they want to. The password is not on this
    # list, for the reason `choosable` gives.
    choosable=frozenset({USER, DATABASE}),
    environment={
        "POSTGRES_USER": USER,
        "POSTGRES_PASSWORD": PASSWORD,
        "POSTGRES_DB": DATABASE,
    },
    command=(),
    adapter_type="postgres",
    connector_options={
        "auth_method": Fixed("user_password"),
        "host": HOST,
        "port": PORT,
        "database": DATABASE,
        "user": USER,
        "password": PASSWORD,
    },
    startup_timeout_seconds=120,
)


# Everything this server may be asked to start. A tuple rather than a registry
# with a `register` decorator: an adapter type is registered by the module that
# implements a driver, and there is nothing to implement here. A template is
# data, and data that can be added to at runtime is data a test cannot pin
# down.
REDIS = ServiceTemplate(
    key="redis",
    title="Redis",
    description=(
        "An in-memory key-value server of its own, started on this machine "
        "with a password nobody has to choose."
    ),
    image="redis:8",
    container_port=6379,
    # Where the image writes its snapshots, which is the only state it keeps.
    data_path="/data",
    credentials={PASSWORD: Generated()},
    # A Redis server has no user and no named database — the sixteen it has
    # are numbered — so there is nothing here anybody could name.
    choosable=frozenset(),
    # Nothing. The official image has no variable for a password: it is told
    # on the command line, which is the whole reason `command` takes values.
    environment={},
    command=(Fixed("redis-server"), Fixed("--requirepass"), PASSWORD),
    adapter_type="redis",
    connector_options={
        "auth_method": Fixed("password"),
        "host": HOST,
        "port": PORT,
        "password": PASSWORD,
    },
    # It answers as soon as it is up; there is no data directory to build.
    startup_timeout_seconds=60,
)


SERVICE_TEMPLATES: tuple[ServiceTemplate, ...] = (POSTGRES, REDIS)

_BY_KEY = {template.key: template for template in SERVICE_TEMPLATES}


def template_for(key: str) -> ServiceTemplate:
    """The template a key names, or a refusal.

    The one place a string from a client becomes a template. Nothing else
    accepts a key, so there is no second door where a name could resolve
    differently.
    """
    try:
        return _BY_KEY[key]
    except KeyError:
        raise UnknownServiceTemplate(key) from None


def all_templates() -> tuple[ServiceTemplate, ...]:
    return SERVICE_TEMPLATES


def choosable_slots(template: ServiceTemplate) -> tuple[CredentialSlot, ...]:
    """Which of a template's credentials a requester may name themselves.

    In the order the slots are declared in, so a form built from this asks for
    them in the same order every time.
    """
    return tuple(slot for slot in CREDENTIAL_SLOTS if slot in template.choosable)


def generated_slots(template: ServiceTemplate) -> tuple[CredentialSlot, ...]:
    """Which of a template's credentials this server makes up.

    Derived from the declaration rather than declared beside it: a list and an
    implementation that can disagree eventually do.
    """
    return tuple(
        slot
        for slot in CREDENTIAL_SLOTS
        if isinstance(template.credentials.get(slot), Generated)
    )
