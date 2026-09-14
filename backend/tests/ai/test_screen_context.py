import uuid

import pytest
from pydantic import ValidationError

from app.ai.models import ConversationMessageCreate, ScreenContext
from app.ai.runner import message_with_context


def test_message_context_carries_identity_but_no_panel_content() -> None:
    connector_id = uuid.uuid4()
    context = ScreenContext(
        panel_id="rows:one:orders",
        label="orders · Rows",
        kind="rows",
        connector_id=connector_id,
        node_id="public.orders",
    )

    rendered = message_with_context("Summarize this", [context])

    assert rendered.startswith("Summarize this\n\nSelected workspace tabs:")
    assert "orders · Rows" in rendered
    assert str(connector_id) in rendered
    assert "public.orders" in rendered


def test_message_accepts_at_most_five_contexts() -> None:
    contexts = [
        {"panel_id": f"panel-{number}", "label": f"Panel {number}", "kind": "rows"}
        for number in range(6)
    ]

    with pytest.raises(ValidationError):
        ConversationMessageCreate(text="Read these", contexts=contexts)
