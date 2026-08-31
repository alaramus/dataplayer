import uuid
from datetime import UTC, datetime

from app.connectors.content_tickets import (
    ContentStreamClaims,
    ImagePreviewClaims,
    content_disposition,
    issue_content_ticket,
    issue_stream_ticket,
    read_content_ticket,
)


def test_ticket_purpose_cannot_be_changed_after_it_is_signed() -> None:
    ticket = issue_content_ticket(
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        node_id="picture.png",
    )

    claims = read_content_ticket(ticket)

    assert isinstance(claims, ImagePreviewClaims)
    assert claims.purpose == "image_preview"


def test_an_expired_content_ticket_is_refused() -> None:
    ticket = issue_content_ticket(
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


def test_a_stream_ticket_carries_the_representation_it_was_minted_for() -> None:
    """One for a sound file cannot be redeemed for a recording (D52)."""
    ticket = issue_stream_ticket(
        representation="audio",
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        node_id="tone.wav",
    )

    claims = read_content_ticket(ticket)

    assert isinstance(claims, ContentStreamClaims)
    assert claims.representation == "audio"
    assert claims.node_id == "tone.wav"


def test_the_two_kinds_of_ticket_are_told_apart_by_their_purpose() -> None:
    stream = read_content_ticket(
        issue_stream_ticket(
            representation="pdf",
            user_id=uuid.UUID(int=1),
            connector_id=uuid.UUID(int=2),
            node_id="report.pdf",
        )
    )
    preview = read_content_ticket(
        issue_content_ticket(
            user_id=uuid.UUID(int=1),
            connector_id=uuid.UUID(int=2),
            node_id="picture.png",
        )
    )

    assert isinstance(stream, ContentStreamClaims)
    assert isinstance(preview, ImagePreviewClaims)


def test_an_expired_stream_ticket_is_refused() -> None:
    ticket = issue_stream_ticket(
        representation="video",
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        node_id="clip.mp4",
        now=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert read_content_ticket(ticket) is None
