"""The ranged byte route: what a player asks for, and what it is told (D52)."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.content_tickets import issue_content_ticket, issue_stream_ticket
from app.core.config import settings
from app.users import crud, storage
from tests.utils.media import mp4_bytes, pdf_bytes, wav_bytes

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    wav_bytes(home / "tone.wav", seconds=1, rate=8000, channels=1)
    (home / "clip.mp4").write_bytes(mp4_bytes(timescale=1000, duration=2500))
    (home / "report.pdf").write_bytes(pdf_bytes())
    (home / "notes.txt").write_text("first\n")
    return home


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"media {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _stream_url(
    client: AsyncClient, headers: dict[str, str], connector_id: str, node_id: str,
    representation: str,
) -> str:
    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=headers,
        json={"node_id": node_id, "representation": representation},
    )
    assert response.status_code == 200, response.text
    url = response.json()["stream_url"]
    assert isinstance(url, str)
    return url


@pytest.mark.usefixtures("home")
async def test_a_sound_file_answers_with_its_verified_facts_and_a_stream(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "tone.wav", "representation": "audio"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "audio"
    assert body["media_type"] == "audio/wav"
    assert body["sample_rate"] == 8000
    assert body["duration_seconds"] == pytest.approx(1.0)
    assert body["stream_url"].startswith(f"{BASE}/content-streams/")


@pytest.mark.usefixtures("home")
async def test_the_whole_body_is_answered_when_no_range_is_asked_for(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    url = await _stream_url(
        client, normal_user_token_headers, connector_id, "tone.wav", "audio"
    )

    response = await client.get(url)

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == (home / "tone.wav").read_bytes()


@pytest.mark.usefixtures("home")
async def test_a_range_is_answered_with_exactly_those_bytes(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    url = await _stream_url(
        client, normal_user_token_headers, connector_id, "tone.wav", "audio"
    )
    whole = (home / "tone.wav").read_bytes()

    response = await client.get(url, headers={"Range": "bytes=100-199"})

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 100-199/{len(whole)}"
    assert response.headers["content-length"] == "100"
    assert response.content == whole[100:200]


@pytest.mark.usefixtures("home")
async def test_the_last_bytes_are_answered_first_when_a_player_asks_for_them(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    """An MP4 keeps its index at the end, so this is the first request made."""
    connector_id = await _connector(client, normal_user_token_headers)
    url = await _stream_url(
        client, normal_user_token_headers, connector_id, "clip.mp4", "video"
    )
    whole = (home / "clip.mp4").read_bytes()

    response = await client.get(url, headers={"Range": "bytes=-64"})

    assert response.status_code == 206
    assert response.content == whole[-64:]


@pytest.mark.usefixtures("home")
async def test_bytes_that_are_not_there_are_refused_with_the_size(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    url = await _stream_url(
        client, normal_user_token_headers, connector_id, "tone.wav", "audio"
    )
    size = (home / "tone.wav").stat().st_size

    response = await client.get(url, headers={"Range": f"bytes={size + 10}-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


@pytest.mark.usefixtures("home")
async def test_a_pdf_is_streamed_by_the_same_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    described = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "report.pdf", "representation": "pdf"},
    )
    assert described.json()["version"] == "1.7"

    response = await client.get(described.json()["stream_url"])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")


@pytest.mark.usefixtures("home")
async def test_a_ticket_for_one_representation_is_not_authority_for_another(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    ticket = issue_stream_ticket(
        representation="audio",
        user_id=user.id,
        connector_id=uuid.UUID(connector_id),
        node_id="clip.mp4",
    )

    response = await client.get(f"{BASE}/content-streams/{ticket}")

    assert response.status_code == 404


@pytest.mark.usefixtures("home")
async def test_a_preview_ticket_is_not_a_stream_ticket(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    ticket = issue_content_ticket(
        user_id=user.id,
        connector_id=uuid.UUID(connector_id),
        node_id="tone.wav",
    )

    response = await client.get(f"{BASE}/content-streams/{ticket}")

    assert response.status_code == 404


@pytest.mark.usefixtures("home")
async def test_a_stream_ticket_is_not_a_preview_ticket(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    ticket = issue_stream_ticket(
        representation="audio",
        user_id=user.id,
        connector_id=uuid.UUID(connector_id),
        node_id="tone.wav",
    )

    response = await client.get(f"{BASE}/content-files/{ticket}")

    assert response.status_code == 404


async def test_a_ticket_nobody_signed_is_not_content(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/content-streams/not-a-ticket")

    assert response.status_code == 404


@pytest.mark.usefixtures("home")
async def test_a_text_file_offers_no_stream(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt", "representation": "text"},
    )

    assert response.status_code == 200
    assert "stream_url" not in response.json()
