"""What the log keeps, and what it never keeps (D184)."""

import io
import json
import logging
from pathlib import Path

import pytest

from app.core import logs
from app.core.config import settings

PASSWORD = "Sup3r-secret"


@pytest.mark.parametrize(
    "text",
    [
        f"connection to postgresql://ann:{PASSWORD}@db:5432/app failed",
        f"invalid dsn: host=db user=ann password={PASSWORD} dbname=app",
        f"invalid dsn: host=db password='{PASSWORD}'",
        f'{{"user": "ann", "password": "{PASSWORD}"}}',
        f'"GET /api/v1/connectors/1/download?ticket={PASSWORD} HTTP/1.1" 200',
        f"PGPASSWORD={PASSWORD}",
        f"Authorization: Bearer {PASSWORD}",
        f"redis://:{PASSWORD}@cache:6379/0",
    ],
)
def test_a_secret_is_masked_however_it_is_spelled(text: str) -> None:
    masked = logs.redact(text)

    assert PASSWORD not in masked
    assert "***" in masked


def test_ordinary_text_is_left_alone() -> None:
    text = "Job 42 (paste.transfer) failed: 3 of 10 files copied"

    assert logs.redact(text) == text


def _record(
    message: str, *, failure: BaseException | None = None, ref: str | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(
        "app.test",
        logging.ERROR,
        __file__,
        1,
        message,
        None,
        None if failure is None else (type(failure), failure, failure.__traceback__),
    )
    if ref is not None:
        record.ref = ref
    return record


def _failure() -> BaseException:
    try:
        raise RuntimeError(f"could not connect to postgresql://ann:{PASSWORD}@db/app")
    except RuntimeError as failure:
        return failure


def test_a_json_line_says_when_where_what_and_why_and_masks_it() -> None:
    token = logs.current_request.set("GET /api/v1/connectors/")
    try:
        line = logs.JsonLines("backend").format(
            _record("A request failed", failure=_failure(), ref="K7Q3PD")
        )
    finally:
        logs.current_request.reset(token)

    entry = json.loads(line)
    assert entry["process"] == "backend"
    assert entry["level"] == "ERROR"
    assert entry["message"] == "A request failed"
    assert entry["ref"] == "K7Q3PD"
    assert entry["request"] == "GET /api/v1/connectors/"
    assert "RuntimeError" in entry["exception"]
    assert PASSWORD not in line


def test_standard_output_carries_the_ref_and_masks_the_traceback() -> None:
    formatter = logs.RedactedText("%(levelname)s %(message)s")

    text = formatter.format(_record("A request failed", failure=_failure(), ref="K7Q3PD"))

    assert text.startswith("ERROR A request failed · ref K7Q3PD")
    assert "Traceback" in text
    assert PASSWORD not in text


def test_a_private_failure_keeps_its_type_and_place_and_not_its_words(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR, logger="app.test")
    # Built at run time: the frames show the line that raised it, which is
    # code, and the words must not be part of that line.
    words = " ".join(["what", "the", "conversation", "said"])
    try:
        raise RuntimeError(words)
    except RuntimeError as raised:
        failure = raised

    ref = logs.record_failure(
        logging.getLogger("app.test"), "An answer failed", failure, private=True
    )

    [record] = [one for one in caplog.records if one.name == "app.test"]
    assert record.getMessage().startswith("An answer failed: RuntimeError")
    assert "test_logs.py" in record.getMessage()
    assert words not in record.getMessage()
    assert record.exc_info is None
    assert getattr(record, "ref", None) == ref
    assert len(ref) == 6


def test_the_health_check_and_the_panel_reading_the_log_are_not_written_down() -> None:
    skip = logs.SkipRoutineReads()

    def access(path: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1", "GET", path, "1.1", 200),
            None,
        )

    assert not skip.filter(access("/api/v1/utils/health-check/"))
    assert not skip.filter(access("/api/v1/logs/?level=all&process=all"))
    assert skip.filter(access("/api/v1/jobs/"))
    # A service's own log is a person's request, not the panel's.
    assert skip.filter(access("/api/v1/services/7/logs"))


def test_an_access_line_keeps_the_path_and_drops_the_words_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The words of a search travel in a query string, and are never kept (D63)."""
    monkeypatch.setattr(settings, "LOG_DIR", tmp_path)
    printed = io.StringIO()
    monkeypatch.setattr("sys.stdout", printed)
    try:
        logs.configure("backend")
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:1",
            "GET",
            "/api/v1/queries/documents?search=zebrafinch&limit=5",
            "1.1",
            200,
        )
    finally:
        monkeypatch.setattr(settings, "LOG_DIR", None)
        logs.configure("backend")

    written = (tmp_path / "backend.log").read_text(encoding="utf-8")
    assert "/api/v1/queries/documents" in written
    assert "zebrafinch" not in written
    assert "zebrafinch" not in printed.getvalue()
    assert "GET /api/v1/queries/documents HTTP/1.1" in printed.getvalue()


def test_a_process_writes_its_own_file_of_json_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LOG_DIR", tmp_path)
    monkeypatch.setattr("sys.stdout", io.StringIO())
    try:
        logs.configure("metrics")
        logging.getLogger("app.test").warning("A datagram could not be stored")
        logging.getLogger("uvicorn.access").info("a request")
    finally:
        monkeypatch.setattr(settings, "LOG_DIR", None)
        logs.configure("backend")

    lines = (tmp_path / "metrics.log").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert [(one["process"], one["logger"], one["message"]) for one in entries] == [
        ("metrics", "app.test", "A datagram could not be stored"),
        ("metrics", "uvicorn.access", "a request"),
    ]
