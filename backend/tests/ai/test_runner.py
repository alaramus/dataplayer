"""What the runner decides on its own: restarts, stream pieces, titles."""

from langchain_core.messages import AIMessage, AIMessageChunk
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import conversations
from app.ai.models import AgentRun, AgentStep
from app.ai.runner import clean_title, model_chunk, split_text
from tests.utils.user import create_random_user


async def test_a_restart_interrupts_what_was_being_written_and_keeps_a_pause(
    db: AsyncSession,
) -> None:
    owner = await create_random_user(db)
    conversation = await conversations.create(db, owner.id)
    writing = await conversations.record_run(
        db, conversation_id=conversation.id, owner_id=owner.id, model_key="openai:x"
    )
    await conversations.start_step(db, writing.id, 0, "thinking", "Thinking")
    paused = await conversations.record_run(
        db, conversation_id=conversation.id, owner_id=owner.id, model_key="openai:x"
    )
    paused.status = "awaiting_answer"
    db.add(paused)
    await db.commit()

    await conversations.recover_interrupted(db)

    await db.refresh(writing)
    await db.refresh(paused)
    step = await db.get(AgentStep, (writing.id, 0))
    assert writing.status == "interrupted"
    assert writing.finished_at is not None
    assert step is not None and step.status == "cancelled"
    # Answering a pause after a restart continues the run (D137).
    assert paused.status == "awaiting_answer"
    assert (await db.get(AgentRun, paused.id)) is not None


def test_only_the_models_own_pieces_are_the_answer() -> None:
    chunk = AIMessageChunk(content="hi")

    assert model_chunk({"type": "messages", "data": (chunk, {"langgraph_node": "model"})}) is chunk
    assert model_chunk({"type": "messages", "data": (chunk, {"langgraph_node": "tools"})}) is None
    assert model_chunk({"type": "updates", "data": {"model": {}}}) is None
    assert model_chunk("not an item") is None


def test_text_and_reasoning_are_told_apart() -> None:
    message = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "first I think"},
            {"type": "text", "text": "then "},
            {"type": "text", "text": "I answer"},
        ]
    )

    assert split_text(message) == ("then I answer", "first I think")
    assert split_text(AIMessage(content="plain")) == ("plain", "")


def test_a_title_is_one_clean_line() -> None:
    assert clean_title('\n  "**Orders by month**."  \nmore') == "Orders by month"
    assert clean_title("#  Заказы за сентябрь") == "Заказы за сентябрь"
    assert clean_title("   ") == ""
    assert len(clean_title("x" * 300)) == 80


def test_the_first_line_stands_in_until_then() -> None:
    assert conversations.first_line_title("\n\n  Count rows \nplease") == "Count rows"
    assert conversations.first_line_title("   ") == "New chat"
    assert len(conversations.first_line_title("y" * 500)) == 200
