import uuid
from datetime import UTC, datetime

from app.connectors.content_tickets import (
    content_disposition,
    issue_content_ticket,
    read_content_ticket,
)


def test_ticket_purpose_cannot_be_changed_after_it_is_signed() -> None:
    ticket = issue_content_ticket(
        purpose="image_preview",
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        node_id="picture.png",
    )

    claims = read_content_ticket(ticket)

    assert claims is not None
    assert claims.purpose == "image_preview"


def test_an_expired_content_ticket_is_refused() -> None:
    ticket = issue_content_ticket(
        purpose="image_preview",
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        node_id="picture.png",
        now=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert read_content_ticket(ticket) is None


def test_content_disposition_keeps_unicode_out_of_the_ascii_fallback() -> None:
    disposition = content_disposition("звіт 2026.png", inline=False)

    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    disposition.encode("ascii")
