"""What PostgreSQL and Redis report about themselves (D128), against real servers."""

from app.adapters import registry
from app.adapters.metrics import MetricSample, SupportsMetrics
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.redis.adapter import RedisAdapter
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import redis_options


def _by_series(samples: list[MetricSample]) -> dict[tuple[str, str, str], MetricSample]:
    return {(one.metric, one.field, one.label): one for one in samples}


async def test_a_postgres_database_reports_its_counters_sessions_and_size() -> None:
    adapter = PostgresAdapter(PostgresUserPassword(**working_postgres_options()))

    samples = _by_series(list(await adapter.metric_samples()))

    commits = samples[("transactions", "commits", "")]
    assert commits.counter is True
    size = samples[("database", "size", "")]
    assert size.counter is False and size.unit == "B" and size.value > 0
    # This very poll is a session of the database.
    assert samples[("sessions", "count", "total")].value >= 1


async def test_a_redis_server_reports_clients_memory_and_commands() -> None:
    samples = _by_series(list(await RedisAdapter(redis_options()).metric_samples()))

    assert samples[("clients", "connected", "")].value >= 1
    assert samples[("memory", "used", "")].unit == "B"
    assert samples[("commands", "processed", "")].counter is True


def test_the_capability_is_read_off_the_driver() -> None:
    reporting = {
        name
        for name in ("postgres", "redis", "file")
        if issubclass(registry.get(name).adapter_class, SupportsMetrics)
    }
    codes = {capability.code for capability in registry.capabilities_of(registry.get("postgres"))}

    assert reporting == {"postgres", "redis"}
    assert "metrics" in codes


def test_every_declared_layout_names_metrics_its_source_reports() -> None:
    from app.adapters.postgres import metrics as postgres
    from app.adapters.redis import metrics as redis

    reported = {
        "postgres": {metric for metric, *_ in postgres._COLUMNS} | {"sessions"},
        "redis": {metric for metric, *_ in redis._FIELDS} | {"databases"},
    }
    for name, presets in (("postgres", postgres.PRESETS), ("redis", redis.PRESETS)):
        for preset in presets:
            for recipe in preset.recipes:
                assert recipe.metric in reported[name], (preset.key, recipe.title)
