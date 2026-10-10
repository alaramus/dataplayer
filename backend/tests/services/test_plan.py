"""What would be created for one service, and where every part of it came from."""

from uuid import uuid4

import pytest

from app.adapters import options as adapter_options
from app.adapters import registry
from app.services.plan import (
    OWNER_LABEL,
    PASSWORD_ALPHABET,
    PASSWORD_LENGTH,
    SERVICE_LABEL,
    TEMPLATE_LABEL,
    Endpoint,
    Placement,
    build_plan,
    connector_options,
    settle_credentials,
    settled_names,
)
from app.services.templates import SERVICE_TEMPLATES, template_for


def _plan(placement: Placement | None = None):
    return build_plan(
        template_for("postgres"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=placement if placement is not None else Placement(),
    )


def test_the_container_is_the_template_and_nothing_else() -> None:
    template = template_for("postgres")

    plan = _plan()

    assert plan.container.image == template.image
    assert plan.container.command == template.command
    assert plan.container.container_port == template.container_port
    assert plan.container.data_path == template.data_path
    assert set(plan.container.environment) == set(template.environment)


def test_a_placement_decides_the_network_and_a_request_never_does() -> None:
    plan = _plan(Placement(network="dataplayer_default", publish=True))

    assert plan.container.network == "dataplayer_default"
    assert plan.container.publish is True
    # No number unless somebody named one: which port is free is the runtime's
    # to answer, and this application would have to bind a socket to find out.
    assert plan.container.host_port is None


def test_a_port_somebody_named_is_the_one_the_container_asks_for() -> None:
    """The one number about a container a request may carry: somebody who has
    a configuration file pointing at 5433 wants 5433."""
    plan = _plan(Placement(network="dataplayer_default", publish=True, host_port=5433))

    assert plan.container.host_port == 5433


def test_a_port_is_meaningless_without_a_port_on_the_host_at_all() -> None:
    """Not carried forward as a number nothing will bind: a spec that named a
    port it does not publish is a spec two readers would read differently."""
    plan = _plan(Placement(publish=False, host_port=5433))

    assert plan.container.publish is False
    assert plan.container.host_port is None


def test_a_service_that_is_not_published_says_so_rather_than_guessing() -> None:
    plan = _plan()

    assert plan.container.publish is False
    assert plan.container.network is None


def test_the_volume_is_named_and_no_path_on_the_host_is_ever_mentioned() -> None:
    """A bind mount is the thing that would put the file system in reach."""
    plan = _plan()

    assert plan.container.volume.startswith("dataplayer-svc-postgres-")
    assert plan.container.data_path.startswith("/")
    written = f"{plan.container!r} {plan.container.volume} {plan.container.name}"
    assert ":/" not in written


def test_the_container_and_its_volume_are_named_after_the_service() -> None:
    plan = _plan()
    short = plan.service_id.hex[:12]

    assert plan.container.name == f"dataplayer-svc-postgres-{short}"
    assert plan.container.volume == f"{plan.container.name}-data"


def test_two_services_of_one_kind_do_not_collide() -> None:
    first, second = _plan(), _plan()

    assert first.container.name != second.container.name
    assert first.container.volume != second.container.volume


def test_the_labels_say_whose_it_is_and_what_made_it() -> None:
    """What a later sweep for orphans matches on: a name is for people."""
    service_id, owner_id = uuid4(), uuid4()

    plan = build_plan(
        template_for("postgres"),
        service_id=service_id,
        owner_id=owner_id,
        placement=Placement(),
    )

    assert plan.container.labels == {
        SERVICE_LABEL: str(service_id),
        TEMPLATE_LABEL: "postgres",
        OWNER_LABEL: str(owner_id),
    }


def test_the_password_is_made_here_and_is_different_every_time() -> None:
    first = settle_credentials(template_for("postgres"))
    second = settle_credentials(template_for("postgres"))

    assert first["password"] != second["password"]
    assert len(first["password"]) == PASSWORD_LENGTH
    assert set(first["password"]) <= set(PASSWORD_ALPHABET)


def test_what_is_not_generated_is_the_same_for_every_service() -> None:
    first = settle_credentials(template_for("postgres"))
    second = settle_credentials(template_for("postgres"))

    assert first["user"] == second["user"] == "dataplayer"
    assert first["database"] == second["database"] == "dataplayer"


def test_the_container_is_started_with_the_password_the_plan_holds() -> None:
    """Read from two places, the two could differ: a container started with
    one password and a connector saved with another."""
    plan = _plan()

    assert plan.container.environment["POSTGRES_PASSWORD"] == plan.credentials[
        "password"
    ]
    assert plan.container.environment["POSTGRES_USER"] == plan.credentials["user"]
    assert plan.container.environment["POSTGRES_DB"] == plan.credentials["database"]


def test_neither_the_plan_nor_the_container_prints_the_password() -> None:
    """One traceback with a spec in a local variable would put it in a log."""
    plan = _plan()

    assert plan.credentials["password"] not in repr(plan)
    assert plan.credentials["password"] not in repr(plan.container)
    assert plan.credentials["password"] not in str(plan.container)


def test_the_connector_it_becomes_validates_as_that_adapter_would() -> None:
    """A service becomes a connector through the adapter's own options model,
    exactly as one somebody typed."""
    plan = _plan(Placement(network="dataplayer_default", publish=True))

    filled = connector_options(plan, Endpoint(host=plan.container.name, port=5432))
    validated = adapter_options.validate(
        registry.get(plan.template.adapter_type).options_schema, filled
    )

    assert filled["host"] == plan.container.name
    assert filled["port"] == 5432
    assert filled["user"] == "dataplayer"
    assert validated.password.get_secret_value() == plan.credentials[
        "password"
    ]


def test_the_secret_of_that_connector_is_a_secret_of_the_model() -> None:
    """So D4's split puts it in the encrypted blob without being told."""
    for template in SERVICE_TEMPLATES:
        schema = registry.get(template.adapter_type).options_schema
        secret_fields = adapter_options.secret_field_names(schema)

        generated = {
            field
            for field, value in template.connector_options.items()
            if value == "password"
        }
        assert generated <= secret_fields, template.key


@pytest.mark.parametrize("key", [template.key for template in SERVICE_TEMPLATES])
def test_no_template_prints_its_password_anywhere(key: str) -> None:
    """One image takes its password on the command line, so the check is made
    for every template rather than for the first one."""
    plan = build_plan(
        template_for(key),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
    )

    password = plan.credentials.get("password")
    assert password is not None
    assert password not in repr(plan)
    assert password not in repr(plan.container)


def test_a_command_carries_what_the_template_said_it_would() -> None:
    """Redis has no environment variable for a password: the image is told on
    the command line, which is why a command is written as values."""
    plan = build_plan(
        template_for("redis"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
    )

    assert plan.container.command == (
        "redis-server",
        "--requirepass",
        plan.credentials["password"],
    )
    assert plan.container.environment == {}


def test_a_password_somebody_typed_is_the_one_the_container_gets() -> None:
    """Not generated and then overwritten somewhere later: the plan is what
    the container is started with and what the connector is filled from, so a
    chosen password has to arrive here or nowhere (D83)."""
    plan = build_plan(
        template_for("postgres"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
        chosen={"password": "s3cret-enough"},
    )

    assert plan.credentials["password"] == "s3cret-enough"
    assert plan.container.environment["POSTGRES_PASSWORD"] == "s3cret-enough"


def test_a_service_asked_to_run_without_one_settles_no_password_at_all() -> None:
    """Not a password made and then left out of the container: a secret that
    exists and is unused is a secret in a log waiting to happen."""
    plan = build_plan(
        template_for("redis"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
        protected=False,
    )

    assert "password" not in plan.credentials
    assert plan.container.command == ("redis-server",)


def test_the_connector_of_an_unprotected_service_says_it_authenticates_with_none() -> (
    None
):
    """The command, the environment and the word the connector uses vary
    together, which is why they are one shape rather than three fields."""
    plan = build_plan(
        template_for("redis"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
        protected=False,
    )

    filled = connector_options(plan, Endpoint(host=plan.container.name, port=6379))
    validated = adapter_options.validate(
        registry.get(plan.template.adapter_type).options_schema, filled
    )

    assert filled["auth_method"] == "no_auth"
    assert "password" not in filled
    assert validated.auth_method == "no_auth"


def test_a_template_that_has_no_unprotected_shape_refuses_to_take_one() -> None:
    """A PostgreSQL that trusts every connection is not a service this server
    will start, and saying so beats quietly making a password up instead."""
    with pytest.raises(ValueError, match="without a password"):
        build_plan(
            template_for("postgres"),
            service_id=uuid4(),
            owner_id=uuid4(),
            placement=Placement(),
            protected=False,
        )


def test_the_names_of_a_service_can_be_read_without_making_a_password() -> None:
    """What fills the window saying where a service listens. A function called
    to fill a screen must not be one that creates secrets."""
    names = settled_names(template_for("postgres"), {"database": "sales"})

    assert names == {"user": "dataplayer", "database": "sales"}


def test_a_server_signed_into_with_a_key_is_told_its_public_half_and_no_password() -> None:
    """D154: the public half goes to the image, password sign-in is off, and
    the connector names the key rather than holding anything secret."""
    key_id = str(uuid4())
    plan = build_plan(
        template_for("ssh"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(),
        chosen={"key_id": key_id, "public_key": "ssh-ed25519 AAAA dataplayer"},
        keyed=True,
    )

    filled = connector_options(plan, Endpoint(host=plan.container.name, port=2222))
    validated = adapter_options.validate(
        registry.get(plan.template.adapter_type).options_schema, filled
    )

    assert "password" not in plan.credentials
    assert plan.container.environment["PUBLIC_KEY"] == "ssh-ed25519 AAAA dataplayer"
    assert plan.container.environment["PASSWORD_ACCESS"] == "false"
    assert "USER_PASSWORD" not in plan.container.environment
    assert filled["auth_method"] == "key"
    assert filled["key_id"] == key_id
    assert str(validated.key_id) == key_id  # type: ignore[union-attr]  # the key variant, asserted above


def test_a_server_to_be_signed_into_with_a_key_is_not_started_without_one() -> None:
    with pytest.raises(ValueError, match="no key"):
        build_plan(
            template_for("ssh"),
            service_id=uuid4(),
            owner_id=uuid4(),
            placement=Placement(),
            keyed=True,
        )
    with pytest.raises(ValueError, match="cannot be signed into with a key"):
        build_plan(
            template_for("postgres"),
            service_id=uuid4(),
            owner_id=uuid4(),
            placement=Placement(),
            keyed=True,
        )
