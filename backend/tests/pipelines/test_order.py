"""The order a pipeline's links run in: arrows first, then position (D177)."""

import uuid

from app.pipelines.models import Card, CardRow, Link, LinkEnd, PipelineContent
from app.pipelines.order import ordered


def _card(name: str, x: float, y: float = 0, rows: tuple[str, ...] = ("a", "b")) -> Card:
    return Card(
        id=uuid.uuid4(),
        connector_id=uuid.uuid4(),
        connector_name=name,
        x=x,
        y=y,
        rows=[CardRow(node_id=row, label=row) for row in rows],
    )


def _link(title: str, source: Card, target: Card, source_row: str = "a", target_row: str = "a") -> Link:
    return Link(
        id=uuid.uuid4(),
        source=LinkEnd(card_id=source.id, node_id=source_row),
        target=LinkEnd(card_id=target.id, node_id=target_row),
        kind="file_copy",
        title=title,
    )


def _titles(content: PipelineContent) -> list[tuple[int, str]]:
    return [(placed.number, placed.link.title) for placed in ordered(content)]


def test_a_card_is_read_after_the_links_writing_into_it_wherever_it_lies() -> None:
    # Drawn right to left: position alone would run the second link first.
    sales, files, warehouse = _card("Sales", 800), _card("Files", 400), _card("Warehouse", 0)
    save = _link("Save as CSV", sales, files)
    load = _link("Create a table", files, warehouse, source_row="b")

    content = PipelineContent(cards=[sales, files, warehouse], links=[load, save])

    assert _titles(content) == [(1, "Save as CSV"), (2, "Create a table")]
    assert all(placed.circle is None for placed in ordered(content))


def test_links_free_to_go_go_left_then_higher_then_by_row() -> None:
    target = _card("Target", 1000)
    low_left = _card("Low left", 0, 300)
    high_left = _card("High left", 0, 0)
    right = _card("Right", 500, 0)
    content = PipelineContent(
        cards=[target, low_left, high_left, right],
        links=[
            _link("right", right, target),
            _link("low left", low_left, target),
            _link("high left, second row", high_left, target, source_row="b"),
            _link("high left, first row", high_left, target, source_row="a", target_row="b"),
        ],
    )

    assert [title for _, title in _titles(content)] == [
        "high left, first row",
        "high left, second row",
        "low left",
        "right",
    ]


def test_a_circle_is_broken_by_position_and_says_so() -> None:
    files, sales = _card("Files", 0), _card("Sales", 400)
    back = _link("Back", sales, files)
    forth = _link("Forth", files, sales)

    placed = ordered(PipelineContent(cards=[files, sales], links=[back, forth]))

    assert [(one.number, one.link.title) for one in placed] == [(1, "Forth"), (2, "Back")]
    assert placed[0].circle == (
        "Files and Sales write into each other, so the arrows give no first link: "
        "this one goes first because its card is furthest left"
    )
    assert placed[1].circle is None


def test_a_circle_is_broken_where_nothing_outside_it_writes() -> None:
    # A and B write into each other; C reads what B wrote and lies furthest
    # left, but a link after a circle waits for it however it is drawn.
    first, second, third = _card("First", 400), _card("Second", 800), _card("Third", 1200)
    reader = _card("Reader", -500)
    one = _link("One", first, second)
    two = _link("Two", second, first)
    leftmost = _link("Leftmost reader", reader, third)
    feeds = _link("Feeds the reader", second, reader, source_row="b")

    placed = ordered(
        PipelineContent(cards=[first, second, third, reader], links=[leftmost, feeds, two, one])
    )

    assert [one.link.title for one in placed] == ["One", "Two", "Feeds the reader", "Leftmost reader"]
    assert placed[0].circle is not None and placed[0].circle.startswith("First and Second write")
