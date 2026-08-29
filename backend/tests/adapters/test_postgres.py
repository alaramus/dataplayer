import time

from pydantic import SecretStr

from app.adapters import registry
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import (
    PostgresNoAuth,
    PostgresOptions,
    PostgresUserPassword,
)
from app.adapters.postgres.session import CHECK_TIMEOUT_SECONDS, PostgresSession
from tests.utils.database import working_postgres_options
from tests.utils.network import silent_endpoint

WRONG_PASSWORD = "definitely-not-the-password"


def _working_options() -> PostgresUserPassword:
    return PostgresUserPassword(**working_postgres_options())


async def test_check_connection_succeeds() -> None:
    result = await PostgresAdapter(_working_options()).check_connection()

    assert result.ok is True
    assert result.error_kind is None
    assert result.latency_ms is not None and result.latency_ms >= 0


async def test_wrong_password_is_classified_as_auth() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


async def test_unreachable_endpoint_times_out_within_the_budget() -> None:
    with silent_endpoint() as port:
        options = _working_options().model_copy(
            update={"host": "127.0.0.1", "port": port}
        )

        started = time.perf_counter()
        result = await PostgresAdapter(options).check_connection()
        elapsed = time.perf_counter() - started

    assert result.ok is False
    assert result.error_kind == "timeout"
    # Unbounded, psycopg waits about two minutes on an unreachable host.
    assert elapsed < CHECK_TIMEOUT_SECONDS + 2


async def test_missing_database_is_classified_as_config() -> None:
    options = _working_options().model_copy(update={"database": "no_such_database"})

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"


async def test_unknown_user_is_classified_as_auth() -> None:
    options = _working_options().model_copy(update={"user": "no_such_role"})

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


async def test_error_message_never_leaks_the_password() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert WRONG_PASSWORD not in result.message


async def test_adapter_type_is_registered() -> None:
    adapter_type = registry.get("postgres")

    assert adapter_type.title == "PostgreSQL"
    assert adapter_type.options_schema is PostgresOptions


def test_a_postgres_source_exposes_its_registered_actions() -> None:
    from app.adapters.actions import SupportsActions

    adapter = PostgresAdapter(_working_options())

    assert isinstance(adapter, SupportsActions)
    assert [action.name for action in adapter.action_types()] == ["rename_relation"]


def test_connection_string_is_a_url_anyone_can_paste() -> None:
    options = PostgresUserPassword(
        host="db.example", port=6543, database="app", user="ann", password=SecretStr("s")
    )

    assert (
        PostgresAdapter(options).connection_string()
        == "postgresql://ann@db.example:6543/app"
    )


def test_connection_string_never_carries_the_password() -> None:
    """It is shown on screen and copied out; a password in it would travel."""
    secret = "definitely-not-the-password"
    options = _working_options().model_copy(update={"password": SecretStr(secret)})

    assert secret not in PostgresAdapter(options).connection_string()


def test_connection_string_escapes_what_would_change_the_url() -> None:
    """A user or a database named with a slash must not invent a new host."""
    options = PostgresUserPassword(
        host="db.example",
        port=5432,
        database="a/b",
        user="ann@corp",
        password=SecretStr("s"),
    )

    assert (
        PostgresAdapter(options).connection_string()
        == "postgresql://ann%40corp@db.example:5432/a%2Fb"
    )


def test_a_file_source_has_no_connection_string() -> None:
    """The capability protocol is how a source says it has none."""
    from app.adapters.file.adapter import FileAdapter
    from app.adapters.protocol import SupportsConnectionString

    assert not issubclass(FileAdapter, SupportsConnectionString)
    assert issubclass(PostgresAdapter, SupportsConnectionString)


def test_the_variant_that_carries_a_password_sends_it() -> None:
    options = PostgresUserPassword(
        host="db.example", database="app", user="ann", password=SecretStr("s3cret")
    )

    assert "password=s3cret" in PostgresSession(options).conninfo()


def test_the_variant_without_a_password_sends_none() -> None:
    """`trust` and `peer` are real: a password is then not merely empty."""
    options = PostgresNoAuth(host="db.example", database="app", user="ann")

    assert "password" not in PostgresSession(options).conninfo()


def test_the_variant_without_a_password_still_has_an_address() -> None:
    options = PostgresNoAuth(host="db.example", port=6543, database="app", user="ann")

    assert (
        PostgresAdapter(options).connection_string()
        == "postgresql://ann@db.example:6543/app"
    )


async def test_a_server_that_wants_a_password_refuses_the_variant_without_one() -> None:
    """The compose database requires one, so this is the honest half of D-В4.

    What cannot be shown here is the other half — that `no_auth` succeeds
    against a server configured with `trust` — because there is no such server
    in this project. Recorded as a known deviation.
    """
    working = working_postgres_options()
    options = PostgresNoAuth(
        host=working["host"],
        port=working["port"],
        database=working["database"],
        user=working["user"],
    )

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


def test_the_options_schema_offers_both_ways_of_connecting() -> None:
    """A pick list of one is scenery; two is a choice."""
    from app.adapters import options as options_module

    assert options_module.variants(PostgresOptions) == [
        PostgresUserPassword,
        PostgresNoAuth,
    ]


def test_the_password_is_a_secret_of_the_union_as_a_whole() -> None:
    """Declared by one variant, and that is enough to be encrypted."""
    from app.adapters import options as options_module

    assert options_module.secret_field_names(PostgresOptions) == {"password"}


def test_a_draft_is_addressed_by_as_much_of_it_as_there_is() -> None:
    """A form still being filled in has a host and a port and little else.

    Asked of the class: there is no valid options object yet, which is the
    whole reason this exists. The same reason `options_from_url` is a
    classmethod.
    """
    assert (
        PostgresAdapter.draft_connection_string({"host": "db.example", "port": 6543})
        == "postgresql://db.example:6543"
    )


def test_a_draft_grows_a_part_at_a_time() -> None:
    draft = PostgresAdapter.draft_connection_string
    host = {"host": "db.example", "port": 5432}

    assert draft({**host, "user": "ann"}) == "postgresql://ann@db.example:5432"
    assert (
        draft({**host, "user": "ann", "database": "app"})
        == "postgresql://ann@db.example:5432/app"
    )


def test_a_draft_is_escaped_by_the_same_rule_as_a_finished_address() -> None:
    """One grammar, written once: the two must not drift apart in the quoting."""
    options = PostgresUserPassword(
        host="db.example",
        port=5432,
        database="a/b",
        user="ann@corp",
        password=SecretStr("s"),
    )
    finished = PostgresAdapter(options).connection_string()

    assert (
        PostgresAdapter.draft_connection_string(
            {"host": "db.example", "port": 5432, "user": "ann@corp", "database": "a/b"}
        )
        == finished
    )


def test_a_draft_with_no_host_has_no_address_at_all() -> None:
    """Nothing to say is said as nothing, not as `postgresql://`."""
    assert PostgresAdapter.draft_connection_string({"port": 5432}) is None
    assert PostgresAdapter.draft_connection_string({"host": ""}) is None


def test_a_draft_never_carries_the_password() -> None:
    """Half-typed values are still values, and one of them is a secret."""
    secret = "definitely-not-the-password"
    url = PostgresAdapter.draft_connection_string(
        {"host": "db.example", "port": 5432, "user": "ann", "password": secret}
    )

    assert url is not None
    assert secret not in url


def test_a_file_source_describes_no_draft() -> None:
    from app.adapters.file.adapter import FileAdapter
    from app.adapters.protocol import DescribesDraft

    assert not issubclass(FileAdapter, DescribesDraft)
    assert issubclass(PostgresAdapter, DescribesDraft)
