"""Files sent with a message: what is taken, what the model sees, what is kept (D142)."""

import asyncio
import base64
import json
import uuid

import pytest
from httpx import AsyncClient
from langchain_core.messages import HumanMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import conversations
from app.ai.attachments import (
    MAX_FILES,
    MAX_IMAGE_BYTES,
    MAX_TEXT_BYTES,
    AttachmentRefused,
    NewAttachment,
    accept,
    file_name,
    image_type,
    model_content,
)
from app.ai.models import MessageAttachment
from tests.ai.conftest import (
    AI,
    Script,
    Turn,
    new_conversation,
    ready_agent,
    settled,
    text,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
NOTES = b"Order 42 shipped late.\n"


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(client=client, email=random_email(), db=db)
    await ready_agent(client, person)
    return person


def test_an_image_is_told_by_its_bytes_and_nothing_else() -> None:
    assert image_type(PNG) == "image/png"
    assert image_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert image_type(b"GIF89a....") == "image/gif"
    assert image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    # Named and typed as an image, it is still read as what its bytes are.
    assert accept("photo.png", NOTES).kind == "text"


def test_text_is_utf8_and_anything_else_is_refused() -> None:
    assert accept("notes.md", "\ufeffЗаметки".encode()).kind == "text"
    with pytest.raises(AttachmentRefused, match="neither text nor"):
        accept("data.bin", b"\xff\xfe\x00\x01")
    with pytest.raises(AttachmentRefused, match="neither text nor"):
        accept("nul.txt", b"text\x00more")


def test_sizes_are_bounded_per_kind() -> None:
    with pytest.raises(AttachmentRefused, match="larger than 5 MB"):
        accept("big.png", PNG + bytes(MAX_IMAGE_BYTES))
    with pytest.raises(AttachmentRefused, match="larger than 256 KB of text"):
        accept("big.txt", b"a" * (MAX_TEXT_BYTES + 1))


def test_a_name_is_its_last_segment_on_either_platform() -> None:
    assert file_name("../../etc/passwd") == "passwd"
    assert file_name("C:\\Users\\me\\photo.png") == "photo.png"
    assert file_name("") == "attachment"
    assert file_name(None) == "attachment"


def test_the_model_reads_text_files_in_the_text_and_images_beside_it() -> None:
    assert model_content("Just words", []) == "Just words"
    blocks = model_content(
        "What is here?",
        [
            NewAttachment("notes.txt", "text", "text/plain", NOTES),
            NewAttachment("photo.png", "image", "image/png", PNG),
        ],
    )
    assert isinstance(blocks, list)
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"].startswith("What is here?")
    assert 'Attached file "notes.txt"' in blocks[0]["text"]
    assert "Order 42 shipped late." in blocks[0]["text"]
    assert blocks[1] == {
        "type": "image",
        "base64": base64.b64encode(PNG).decode(),
        "mime_type": "image/png",
    }
    # A photo alone is a message too, with no empty text beside it.
    assert model_content("", [NewAttachment("photo.png", "image", "image/png", PNG)]) == [
        {"type": "image", "base64": base64.b64encode(PNG).decode(), "mime_type": "image/png"}
    ]


async def test_a_message_carries_its_files_to_the_model_and_keeps_them(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    script.turns += [Turn(pieces=[text("Seen.")]), Turn(pieces=[text("A title")])]
    conversation_id = await new_conversation(client, headers)

    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        data={"text": "What is here?"},
        files=[
            ("files", ("photo.png", PNG, "image/png")),
            ("files", ("notes.txt", NOTES, "text/plain")),
        ],
    )
    assert response.status_code == 202, response.text
    await settled(client, headers, response.json()["id"])

    human = next(one for one in script.calls[0] if isinstance(one, HumanMessage))
    assert isinstance(human.content, list)
    assert "Order 42 shipped late." in str(human.content[0])
    assert human.content[1] == {
        "type": "image",
        "base64": base64.b64encode(PNG).decode(),
        "mime_type": "image/png",
    }

    conversation = (
        await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)
    ).json()
    sent = conversation["messages"][0]
    assert sent["content"] == "What is here?"
    assert await conversations.has_image_attachment(db, uuid.UUID(conversation_id))
    assert [
        (one["name"], one["kind"], one["media_type"], one["size"]) for one in sent["attachments"]
    ] == [("photo.png", "image", "image/png", len(PNG)), ("notes.txt", "text", "text/plain", len(NOTES))]

    photo_id, notes_id = (one["id"] for one in sent["attachments"])
    photo = await client.get(
        f"{AI}/conversations/{conversation_id}/attachments/{photo_id}", headers=headers
    )
    notes = await client.get(
        f"{AI}/conversations/{conversation_id}/attachments/{notes_id}", headers=headers
    )
    assert (photo.status_code, photo.headers["content-type"], photo.content) == (
        200, "image/png", PNG
    )
    assert notes.headers["content-type"] == "text/plain; charset=utf-8"
    assert notes.content == NOTES
    assert notes.headers["x-content-type-options"] == "nosniff"

    # Sealed like the text: neither the name nor the bytes are stored plain.
    stored = (await db.exec(select(MessageAttachment))).all()
    kept = [row for row in stored if row.size == len(NOTES)]
    assert kept
    assert all(NOTES not in row.content and b"notes.txt" not in row.name for row in kept)


async def test_tabs_and_files_travel_in_one_form(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    """The tabs are a JSON field beside the files; read as a list, it was refused."""
    script.turns += [Turn(pieces=[text("Both.")]), Turn(pieces=[text("A title")])]
    conversation_id = await new_conversation(client, headers)
    tab = {"panel_id": "rows:one:orders", "label": "orders · Rows", "kind": "rows"}

    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        data={"text": "Compare", "contexts": json.dumps([tab])},
        files=[("files", ("notes.txt", NOTES, "text/plain"))],
    )
    assert response.status_code == 202, response.text
    await settled(client, headers, response.json()["id"])

    human = next(one for one in script.calls[0] if isinstance(one, HumanMessage))
    assert "orders · Rows" in str(human.content)
    assert "Order 42 shipped late." in str(human.content)


async def test_a_photo_alone_is_a_message_and_names_the_chat(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    gate = asyncio.Event()
    script.turns += [Turn(pieces=[text("A cat."), text(" Asleep.")], gate=gate), Turn(pieces=[text("Cat")])]
    conversation_id = await new_conversation(client, headers)

    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        files=[("files", ("cat.png", PNG, "image/png"))],
    )
    listed = (await client.get(f"{AI}/conversations", headers=headers)).json()["data"]
    gate.set()
    await settled(client, headers, response.json()["id"])

    assert response.status_code == 202, response.text
    assert next(one for one in listed if one["id"] == conversation_id)["title"] == "cat.png"


async def test_somebody_elses_file_is_not_found(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    script.turns += [Turn(pieces=[text("Read.")]), Turn(pieces=[text("A title")])]
    conversation_id = await new_conversation(client, headers)
    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        data={"text": "Keep this"},
        files=[("files", ("notes.txt", NOTES, "text/plain"))],
    )
    await settled(client, headers, response.json()["id"])
    conversation = (
        await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)
    ).json()
    attachment_id = conversation["messages"][0]["attachments"][0]["id"]
    stranger = await authentication_token_from_email(client=client, email=random_email(), db=db)

    found = await client.get(
        f"{AI}/conversations/{conversation_id}/attachments/{attachment_id}", headers=stranger
    )

    assert found.status_code == 404


async def test_an_image_is_refused_to_a_model_that_does_not_read_images(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    conversation_id = await new_conversation(client, headers)
    await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"model_key": "deepseek:deepseek-flash"},
    )

    refused = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        data={"text": "Look"},
        files=[("files", ("photo.png", PNG, "image/png"))],
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["message"] == (
        "DeepSeek V4 Flash does not read images; choose a model that does"
    )
    conversation = (
        await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)
    ).json()
    assert conversation["messages"] == []


async def test_what_is_refused_is_refused_before_anything_runs(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    conversation_id = await new_conversation(client, headers)
    url = f"{AI}/conversations/{conversation_id}/messages"

    binary = await client.post(
        url, headers=headers, data={"text": "x"},
        files=[("files", ("data.bin", b"\xff\xfe\x00\x01", "application/octet-stream"))],
    )
    empty = await client.post(url, headers=headers, data={"text": "   "})
    many = await client.post(
        url, headers=headers, data={"text": "x"},
        files=[("files", (f"{number}.txt", NOTES, "text/plain")) for number in range(MAX_FILES + 1)],
    )

    assert binary.json()["detail"]["message"] == (
        "data.bin is neither text nor a PNG, JPEG, WebP or GIF image"
    )
    assert empty.json()["detail"]["message"] == "Write a message or attach a file"
    assert many.json()["detail"]["message"] == f"A message carries at most {MAX_FILES} files"
    assert {binary.status_code, empty.status_code, many.status_code} == {422}
    conversation = (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).json()
    assert conversation["messages"] == []


async def test_the_settings_say_what_a_message_may_carry(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    rules = (await client.get(f"{AI}/settings", headers=headers)).json()["attachments"]

    assert rules["max_files"] == MAX_FILES
    assert rules["max_image_bytes"] == MAX_IMAGE_BYTES
    assert "image/png" in rules["image_types"]
