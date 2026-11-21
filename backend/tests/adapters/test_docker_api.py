"""The Engine API pieces shared by services and the Docker source (D406)."""

import asyncio

import httpx
import pytest

from app.adapters.docker_api.client import (
    EngineClient,
    EngineRefused,
    EngineUnreachable,
)
from app.adapters.docker_api.frames import demultiplexed, frames, stream_failed
from app.adapters.docker_api.hijack import UpgradeRefused, upgrade_request, upgraded


def frame(stream: int, text: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(text).to_bytes(4, "big") + text


def test_frames_keep_the_stream_each_chunk_came_on() -> None:
    body = frame(1, b"out\n") + frame(2, b"err\n")
    assert frames(body) == [("stdout", b"out\n"), ("stderr", b"err\n")]


def test_a_body_without_frames_is_said_to_be_one() -> None:
    assert frames(b"2026-11-21T11:22:12Z line 1\r\n") is None
    # A header whose length runs past the body is not a frame either.
    assert frames(bytes([1, 0, 0, 0, 0, 0, 0, 9]) + b"short") is None


def test_demultiplexed_text_drops_framing_and_blank_lines() -> None:
    assert demultiplexed(frame(1, b"a\n\n") + frame(2, b"b\n")) == ["a", "b"]
    assert demultiplexed(b"plain\nlines\n") == ["plain", "lines"]
    assert demultiplexed(b"") == []


def test_a_progress_stream_failure_is_noticed() -> None:
    assert stream_failed('{"status":"Downloading"}') is False
    assert stream_failed('{"errorDetail":{"message":"denied"},"error":"denied"}')
    assert stream_failed("not json") is False
    assert stream_failed("") is False


async def test_a_versioned_client_prefixes_every_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={})

    client = EngineClient(lambda: httpx.MockTransport(handler), base_url="http://docker")
    await client.at_version("1.41").request("GET", "/info", expected=(200,))
    assert seen == ["/v1.41/info"]


async def test_a_refusal_carries_the_status_and_not_the_daemons_words() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"message": "/var/lib/docker/secret path"})

    client = EngineClient(lambda: httpx.MockTransport(handler), base_url="http://docker")
    with pytest.raises(EngineRefused) as refused:
        await client.request("DELETE", "/volumes/x", expected=(204,))
    assert refused.value.status == 409
    assert "secret" not in str(refused.value)


async def test_no_answer_is_unreachable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = EngineClient(lambda: httpx.MockTransport(handler), base_url="http://docker")
    with pytest.raises(EngineUnreachable):
        await client.request("GET", "/_ping", expected=(200,))


def test_an_upgrade_request_carries_its_body() -> None:
    written = upgrade_request("/exec/abc/start", b'{"Tty":true}')
    assert written.startswith(b"POST /exec/abc/start HTTP/1.1\r\n")
    assert b"Upgrade: tcp\r\n" in written
    assert b"Content-Length: 12\r\n\r\n" in written
    assert written.endswith(b'{"Tty":true}')


async def test_an_upgrade_is_read_up_to_the_stream() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"HTTP/1.1 101 UPGRADED\r\nConnection: Upgrade\r\n\r\nhello")
    await upgraded(reader, 1.0)
    assert await reader.read(5) == b"hello"

    refused = asyncio.StreamReader()
    refused.feed_data(b"HTTP/1.1 404 Not Found\r\n\r\n")
    with pytest.raises(UpgradeRefused):
        await upgraded(refused, 1.0)
