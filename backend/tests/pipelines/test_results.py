"""What a pipeline's links make, as rows of their cards, along a chain (D178)."""

import uuid

import pytest
from pydantic import ValidationError

from app.connectors.paste.models import PasteColumn, PasteKindName
from app.pipelines.models import Card, CardRow, Link, LinkEnd, PipelineContent
from app.pipelines.order import ordered
from app.pipelines.results import Foresight


def _card(name: str, x: float, rows: list[tuple[str | None, str, str | None]]) -> Card:
    return Card(
        id=uuid.uuid4(),
        connector_id=uuid.uuid4(),
        connector_name=name,
        x=x,
        y=0,
        rows=[CardRow(node_id=node, label=label, kind=kind) for node, label, kind in rows],  # type: ignore[arg-type] -- kinds spelt as the literals they are
    )


def _link(kind: PasteKindName, source: LinkEnd, target: LinkEnd, **choices: object) -> Link:
    return Link.model_validate(
        {"id": uuid.uuid4(), "source": source, "target": target, "kind": kind, "title": kind, **choices}
    )


def _end(card: Card, node_id: str | None = None, made_by: Link | None = None) -> LinkEnd:
    return LinkEnd(card_id=card.id, node_id=node_id, made_by=None if made_by is None else made_by.id)


SALES = _card("Sales", 800, [("public.orders", "orders", "table"), ("public", "public", "schema")])
FILES = _card("Files", 400, [("reports", "reports", "directory")])
BACKUP = _card("Backup", 0, [("vault", "vault", "directory")])


def test_a_chain_is_named_link_by_link_from_its_ticked_root() -> None:
    save = _link("relation_csv", _end(SALES, "public.orders"), _end(FILES, "reports"), name="monthly")
    copy = _link("file_copy", _end(FILES, made_by=save), _end(BACKUP, "vault"))
    load = _link(
        "rows_new_relation",
        _end(BACKUP, made_by=copy),
        _end(SALES, "public"),
        name="loaded",
        columns=[PasteColumn(source="id", target="id", type_code="text")],
    )
    into = _link("rows_into_relation", _end(FILES, made_by=save), _end(SALES, made_by=load))
    content = PipelineContent(cards=[SALES, FILES, BACKUP], links=[into, load, copy, save])

    rows = {(row.link_id, row.card_id): (row.name, row.kind) for row in Foresight(content).rows()}

    assert rows == {
        (save.id, FILES.id): ("monthly.csv", "file"),
        (copy.id, BACKUP.id): ("monthly.csv", "file"),
        (load.id, SALES.id): ("loaded", "table"),
    }
    # Each link after the one making what it reads or writes into, wherever
    # its card lies: the backup card is furthest left.
    assert [placed.link.id for placed in ordered(content)] == [save.id, copy.id, load.id, into.id]


def test_a_result_is_a_row_only_of_the_card_its_link_writes_into() -> None:
    save = _link("relation_csv", _end(SALES, "public.orders"), _end(FILES, "reports"))
    fill = _link("rows_into_relation", _end(FILES, "reports"), _end(SALES, "public.orders"))
    base = [SALES, FILES, BACKUP]
    for wrong in (
        _link("file_copy", _end(BACKUP, made_by=save), _end(FILES, "reports")),
        _link("file_copy", _end(FILES, made_by=fill), _end(BACKUP, "vault")),
    ):
        with pytest.raises(ValidationError, match="does not hold"):
            PipelineContent(cards=base, links=[save, fill, wrong])
    with pytest.raises(ValidationError, match="not by a node"):
        LinkEnd(card_id=FILES.id, node_id="reports", made_by=save.id)


def test_a_link_cannot_read_however_far_along_what_it_makes_itself() -> None:
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    first = Link.model_validate({
        "id": first_id, "kind": "file_copy", "title": "Copy",
        "source": {"card_id": FILES.id, "made_by": second_id},
        "target": {"card_id": BACKUP.id, "node_id": "vault"},
    })
    second = Link.model_validate({
        "id": second_id, "kind": "file_copy", "title": "Copy",
        "source": {"card_id": BACKUP.id, "made_by": first_id},
        "target": {"card_id": FILES.id, "node_id": "reports"},
    })

    with pytest.raises(ValidationError, match="what it makes itself"):
        PipelineContent(cards=[FILES, BACKUP], links=[first, second])


def test_a_circle_is_not_broken_at_a_link_reading_a_result() -> None:
    # Sales writes a file into Files, a copy of it goes to Backup, and Backup
    # writes back into Sales. The copy reads a result and lies furthest left,
    # so position alone would start there.
    files = _card("Files", -500, [("reports", "reports", "directory")])
    save = _link("relation_csv", _end(SALES, "public.orders"), _end(files, "reports"))
    back = _link("file_copy", _end(files, made_by=save), _end(BACKUP, "vault"))
    loop = _link("rows_into_relation", _end(BACKUP, "vault"), _end(SALES, "public.orders"))

    placed = ordered(PipelineContent(cards=[SALES, files, BACKUP], links=[back, loop, save]))

    assert [one.link.id for one in placed] == [loop.id, save.id, back.id]
    assert placed[0].circle is not None
