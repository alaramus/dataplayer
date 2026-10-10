"""What this server may start is a closed set written in code (D80)."""

import pytest

from app.adapters import options as adapter_options
from app.adapters import registry
from app.services.templates import (
    CREDENTIAL_SLOTS,
    SERVICE_TEMPLATES,
    Fixed,
    Generated,
    UnknownServiceTemplate,
    all_templates,
    generated_slots,
    may_run_unprotected,
    may_sign_in_with_key,
    shape_of,
    shapes,
    slots_of,
    template_for,
)


def test_a_key_that_names_no_template_does_not_resolve() -> None:
    """The one door a client's string goes through."""
    with pytest.raises(UnknownServiceTemplate):
        template_for("postgres:18; docker run --privileged")


def test_every_template_is_reachable_by_its_own_key() -> None:
    for template in all_templates():
        assert template_for(template.key) is template


def test_keys_are_unique() -> None:
    keys = [template.key for template in SERVICE_TEMPLATES]

    assert sorted(keys) == sorted(set(keys))


def test_no_image_is_a_moving_target() -> None:
    """`latest` is a statement about the day, not about what will run."""
    for template in SERVICE_TEMPLATES:
        assert ":" in template.image, template.key
        assert not template.image.endswith(":latest"), template.key


def test_every_template_becomes_a_source_type_this_server_has() -> None:
    """A template that named a type nobody registered would be a service
    nobody could connect to."""
    for template in SERVICE_TEMPLATES:
        assert registry.get(template.adapter_type).name == template.adapter_type


def test_every_option_a_template_fills_is_a_field_of_that_adapter() -> None:
    """The connector a service becomes goes through the adapter's own schema,
    so a field the model does not have is a mistake to catch here rather than
    at the moment somebody presses the button.

    Every shape, not only the ordinary one: a template that runs without a
    password fills a different set of fields, and it is the one nothing
    exercises by default."""
    for template in SERVICE_TEMPLATES:
        schema = registry.get(template.adapter_type).options_schema
        known = {
            name
            for variant in adapter_options.variants(schema)
            for name in variant.model_fields
        }

        for shape in shapes(template):
            assert set(shape.connector_options) <= known, template.key


def test_every_slot_a_template_uses_is_one_it_settled() -> None:
    """A value the template refers to and never decided would be a KeyError at
    the worst moment."""
    for template in SERVICE_TEMPLATES:
        settled = set(template.credentials)

        for shape in shapes(template):
            assert slots_of(shape) <= settled, template.key


def test_a_shape_without_a_password_refers_to_none() -> None:
    """What makes "no password" mean no secret settled rather than one made
    and then left out of the container."""
    redis = template_for("redis")
    assert redis.unprotected is not None

    assert slots_of(shape_of(redis, protected=True)) == {"password"}
    assert slots_of(redis.unprotected) == set()


def test_a_template_with_no_unprotected_shape_will_not_be_asked_for_one() -> None:
    for template in SERVICE_TEMPLATES:
        assert may_run_unprotected(template) is (template.unprotected is not None)

    with pytest.raises(ValueError, match="without a password"):
        shape_of(template_for("postgres"), protected=False)


def test_what_is_generated_is_read_off_the_declaration() -> None:
    for template in SERVICE_TEMPLATES:
        assert generated_slots(template) == tuple(
            slot
            for slot in CREDENTIAL_SLOTS
            if isinstance(template.credentials.get(slot), Generated)
        )


def test_the_postgres_template_generates_its_password_and_nothing_else() -> None:
    """The point of the whole registry, stated for the one template there is:
    nobody is asked to invent a password, and nobody may choose the image."""
    postgres = template_for("postgres")

    assert generated_slots(postgres) == ("password",)
    assert postgres.image == "postgres:18"
    assert postgres.container_port == 5432
    assert postgres.command == ()
    assert set(postgres.environment) == {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    }


def test_the_timescale_template_is_a_postgresql_source_from_the_extension_image() -> None:
    """A database holding an extension is not another kind of database: what
    it holds is discovered while it is open (D119), so the service becomes an
    ordinary PostgreSQL connector.

    And the extension comes with the image rather than being installed into
    PostgreSQL afterwards: its files have to be on the server and its library
    has to be preloaded, neither of which a connection can arrange for itself.
    """
    timescale = template_for("timescaledb")

    assert timescale.adapter_type == "postgres"
    assert timescale.image.startswith("timescale/timescaledb:")
    assert generated_slots(timescale) == ("password",)
    assert timescale.environment["TIMESCALEDB_TELEMETRY"] == Fixed("off")


def test_two_templates_of_one_source_type_settle_the_same_credentials() -> None:
    """Two ways to a PostgreSQL, and a connector filled the same way by both:
    a template that filled fewer fields would be a connection somebody has to
    finish by hand."""
    postgres = template_for("postgres")
    timescale = template_for("timescaledb")

    assert slots_of(shape_of(timescale, protected=True)) == slots_of(
        shape_of(postgres, protected=True)
    )
    assert timescale.connector_options == postgres.connector_options
    assert timescale.choosable == postgres.choosable


def test_the_ssh_template_is_a_server_signed_into_with_a_password_it_made() -> None:
    """An SSH server as a template (D153): the account
    and its password go to the image, and the connector signs in with both.

    Nothing can say the server's key before the container has made one, so
    no field of the template holds it: the job pins what it presents."""
    ssh = template_for("ssh")

    assert ssh.adapter_type == "ssh"
    assert ssh.image.startswith("lscr.io/linuxserver/openssh-server:")
    assert ssh.data_path == "/config"
    assert generated_slots(ssh) == ("password",)
    assert ssh.choosable == frozenset({"user", "password"})
    assert ssh.environment["USER_NAME"] == "user"
    assert ssh.environment["USER_PASSWORD"] == "password"
    assert ssh.environment["PASSWORD_ACCESS"] == Fixed("true")
    assert "host_key" not in ssh.connector_options
    assert may_run_unprotected(ssh) is False


def test_only_the_ssh_server_is_signed_into_with_a_key() -> None:
    """A key is a way into a machine, not into a database (D154)."""
    ssh = template_for("ssh")
    assert ssh.keyed is not None

    assert [t.key for t in SERVICE_TEMPLATES if may_sign_in_with_key(t)] == ["ssh"]
    assert slots_of(ssh.keyed) == {"user", "key_id", "public_key"}
    assert ssh.keyed.environment["PASSWORD_ACCESS"] == Fixed("false")
    assert ssh.keyed.connector_options["auth_method"] == Fixed("key")
