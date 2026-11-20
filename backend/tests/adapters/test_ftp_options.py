"""The FTP form, its address and its failures (D386)."""

import socket

import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.ftp.adapter import FtpAdapter
from app.adapters.ftp.client import connected
from app.adapters.ftp.options import FtpOptions
from app.adapters.protocol import AdapterError

OPTIONS: TypeAdapter[FtpOptions] = TypeAdapter(FtpOptions)


def _options(**fields: object) -> FtpOptions:
    return OPTIONS.validate_python(
        {
            "auth_method": "password",
            "host": "ftp.example.com",
            "username": "u",
            "password": "p",
            **fields,
        }
    )


def test_an_empty_form_asks_for_explicit_tls_on_port_21() -> None:
    options = _options()

    assert (options.security, options.port, options.verify_tls, options.path) == (
        "explicit",
        21,
        True,
        "",
    )


@pytest.mark.parametrize("host", ["ftp://example.com", "user@example.com", "a/b", ""])
def test_a_host_is_a_name_and_nothing_else(host: str) -> None:
    with pytest.raises(ValidationError):
        _options(host=host)


@pytest.mark.parametrize("field", ["path", "username"])
def test_a_line_break_cannot_become_a_second_command(field: str) -> None:
    with pytest.raises(ValidationError):
        _options(**{field: "pub\r\nDELE secret"})


def test_the_password_is_not_in_what_the_options_show() -> None:
    options = _options(password="hunter2")

    assert "hunter2" not in options.model_dump_json()
    assert "hunter2" not in repr(options)


@pytest.mark.parametrize(
    ("fields", "address"),
    [
        ({}, "ftp://u@ftp.example.com"),
        ({"port": 2121, "path": "pub/data"}, "ftp://u@ftp.example.com:2121/pub/data"),
        ({"path": "/srv/ftp"}, "ftp://u@ftp.example.com//srv/ftp"),
        ({"security": "implicit", "port": 990}, "ftps://u@ftp.example.com"),
        ({"security": "implicit", "port": 21}, "ftps://u@ftp.example.com:21"),
    ],
)
def test_the_address_shown_carries_no_password(
    fields: dict[str, object], address: str
) -> None:
    options = _options(**fields)

    assert (
        FtpAdapter.draft_connection_string(options.model_dump(mode="python")) == address
    )


def test_an_anonymous_address_names_no_user() -> None:
    options = OPTIONS.validate_python(
        {"auth_method": "anonymous", "host": "ftp.gnu.org"}
    )

    assert (
        FtpAdapter.draft_connection_string(options.model_dump(mode="python"))
        == "ftp://ftp.gnu.org"
    )


@pytest.mark.parametrize(
    ("url", "found"),
    [
        (
            "ftp://bob@files.example.com:2121/pub/x",
            {
                "host": "files.example.com",
                "port": 2121,
                "path": "pub/x",
                "username": "bob",
            },
        ),
        (
            "ftp://files.example.com",
            {"host": "files.example.com", "port": 21, "path": ""},
        ),
        (
            "ftp://files.example.com//srv",
            {"host": "files.example.com", "port": 21, "path": "/srv"},
        ),
        (
            "ftps://files.example.com",
            {
                "host": "files.example.com",
                "port": 990,
                "path": "",
                "security": "implicit",
            },
        ),
    ],
)
def test_an_address_fills_the_form(url: str, found: dict[str, object]) -> None:
    assert FtpAdapter.options_from_url(url) == found


@pytest.mark.parametrize(
    "url",
    [
        "ftp://bob:secret@example.com",
        "http://example.com",
        "ftp://example.com/?a=1",
        "ftp://",
    ],
)
def test_an_address_with_a_password_or_not_of_ftp_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        FtpAdapter.options_from_url(url)


def test_an_unreachable_server_is_a_network_failure_that_names_no_address() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    options = _options(host="127.0.0.1", port=port, security="none", password="hunter2")

    with pytest.raises(AdapterError) as raised:
        connected(options)

    assert raised.value.error_kind == "network"
    assert "127.0.0.1" not in raised.value.message
    assert "hunter2" not in raised.value.message
