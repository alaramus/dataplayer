"""A source failure nobody expected is written down whole, with the ref its sentence
carries; an expected one is an answer about the source (D184)."""

import logging

import psycopg
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.adapters.postgres.session import classify
from app.adapters.redis.session import _reduced as redis_reduced
from app.adapters.ssh.session import reduced as ssh_reduced

SECRET = "hunter2"


def _refs(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        str(getattr(record, "ref", ""))
        for record in caplog.records
        if record.levelno == logging.ERROR and record.exc_info is not None
    ]


def test_postgres_answers_the_unexpected_with_the_ref_of_its_log_entry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    kind, message = classify(ValueError(f"password={SECRET}"), fallback_message="Query failed")

    [ref] = _refs(caplog)
    assert kind == "unknown"
    assert message == f"Query failed · ref {ref}"
    assert SECRET not in message


def test_postgres_says_an_unreachable_server_and_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    kind, message = classify(psycopg.OperationalError("connection refused"))

    assert (kind, message) == ("network", "Could not reach the database server")
    assert _refs(caplog) == []


def test_redis_answers_the_unexpected_with_a_ref(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    expected = redis_reduced(RedisConnectionError("refused"))
    unexpected = redis_reduced(RedisError(f"odd {SECRET}"))

    [ref] = _refs(caplog)
    assert expected.message == "Could not reach the Redis server"
    assert unexpected.message == f"The Redis server could not do that · ref {ref}"


def test_ssh_answers_the_unexpected_with_a_ref(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    expected = ssh_reduced(TimeoutError())
    unexpected = ssh_reduced(RuntimeError("odd"))

    [ref] = _refs(caplog)
    assert expected.message == "The server did not answer in time"
    assert unexpected.message == f"The server could not do that · ref {ref}"
