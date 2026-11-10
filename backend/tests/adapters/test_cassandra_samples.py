"""The lab put into a node this server started (D352), and the templates that start one (D351)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters import registry
from app.adapters.cassandra.samples import PAGE_VIEWS, SAMPLE_KEYSPACE, _rows
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.protocol import SupportsSampleData
from app.core.sha512_crypt import sha512_crypt
from app.services.plan import _credential_value
from app.services.templates import SaltedHash, shape_of, slots_of, template_for
from tests.adapters.cassandra_fixture import TARGETS, Target, run


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    yield chosen
    await run(chosen, f"DROP KEYSPACE IF EXISTS {SAMPLE_KEYSPACE}")


# --- The hash a ScyllaDB service is told its password as ---------------------


def test_sha512_crypt_writes_what_glibc_writes() -> None:
    # The test vector of the scheme's own description, and the compose file's.
    assert sha512_crypt("Hello world!", "saltstring") == (
        "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"
    )
    assert sha512_crypt("cassandra", "dataplayer").startswith(
        "$6$dataplayer$gGIHHoZqUhgE4"
    )
    made = sha512_crypt("secret")
    assert made.startswith("$6$") and len(made.split("$")[2]) == 16


def test_a_salted_hash_reads_the_password_and_escapes_for_a_shell() -> None:
    template = template_for("scylladb")
    hashed = template.command[-1]

    assert isinstance(hashed, SaltedHash)
    assert "password" in slots_of(shape_of(template, protected=True))
    value = _credential_value(hashed, {"password": "p"})
    assert value.startswith("--auth-superuser-salted-password=\\$6\\$")
    assert value != "--auth-superuser-salted-password=p"


def test_both_cards_offer_their_own_server() -> None:
    faces = {face.key: face.templates for face in registry.get("cassandra").faces}

    assert faces == {"cassandra": ("cassandra",), "scylladb": ("scylladb",)}
    for key in ("cassandra", "scylladb"):
        template = template_for(key)
        assert template.adapter_type == "cassandra"
        assert template.connector_options["user"] == "user"


def test_the_cassandra_template_never_puts_the_password_in_an_argument() -> None:
    template = template_for("cassandra")

    assert template.environment["DP_PASSWORD"] == "password"
    assert all(not isinstance(part, str) for part in template.command)


# --- The lab -------------------------------------------------------------------


def test_the_lab_is_the_same_every_time() -> None:
    first, second = _rows(), _rows()

    assert first == second
    assert len(first["page_views"]) == PAGE_VIEWS


async def test_the_lab_is_installed_and_read(target: Target) -> None:
    adapter = target.adapter()
    assert isinstance(adapter, SupportsSampleData)

    said = await adapter.install_sample_data()
    tables = {node.name for node in await adapter.list_children(SAMPLE_KEYSPACE)}
    views = await adapter.fetch(
        FetchRequest(node_id=f"{SAMPLE_KEYSPACE}.page_views", limit=1000)
    )
    counters = await adapter.fetch(
        FetchRequest(node_id=f"{SAMPLE_KEYSPACE}.views_by_path")
    )
    done = await adapter.fetch(
        FetchRequest(
            node_id=f"{SAMPLE_KEYSPACE}.tasks_by_status",
            filters=[ScalarFilter(column="status", op="eq", value="done")],
        )
    )

    assert said == "demo_lab: 5 tables"
    assert tables == {
        "organizations",
        "users_by_organization",
        "tasks_by_project",
        "tasks_by_status",
        "page_views",
        "views_by_path",
    }
    assert len(views.rows) == 1000 and views.has_more
    assert sum(int(row[1] or 0) for row in counters.rows) == PAGE_VIEWS
    assert len(done.rows) == 75
    assert not counters.update_supported


async def test_the_lab_can_be_installed_twice(target: Target) -> None:
    adapter = target.adapter()

    await adapter.install_sample_data()
    again = await adapter.install_sample_data()

    assert again == "demo_lab: 5 tables"


# --- Metrics -------------------------------------------------------------------


async def test_a_poll_reads_clients_size_and_on_cassandra_its_pools(
    target: Target,
) -> None:
    adapter = target.adapter()

    samples = {
        (sample.metric, sample.field): sample
        for sample in await adapter.metric_samples()
    }
    presets = [preset.key for preset in type(adapter).metric_presets()]

    assert samples[("sessions", "clients")].value >= 1
    assert ("keyspace", "size") in samples and ("keyspace", "partitions") in samples
    if target.scylla:
        assert ("statements", "reads") not in samples
    else:
        assert samples[("statements", "requests")].counter
        assert ("tasks", "pending") in samples
    assert presets == ["cassandra-node"]
