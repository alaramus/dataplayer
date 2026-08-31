import uuid
from datetime import UTC, datetime

from app.connectors.action_downloads import (
    issue_action_download_ticket,
    read_action_download_ticket,
)


def test_an_action_download_ticket_keeps_the_action_and_whole_selection() -> None:
    ticket = issue_action_download_ticket(
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        action_name="download",
        node_ids=["one.txt", "folder"],
    )

    claims = read_action_download_ticket(ticket)

    assert claims is not None
    assert claims.action_name == "download"
    assert claims.node_ids == ["one.txt", "folder"]


def test_an_expired_action_download_ticket_is_refused() -> None:
    ticket = issue_action_download_ticket(
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        action_name="download",
        node_ids=["one.txt"],
        now=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert read_action_download_ticket(ticket) is None
