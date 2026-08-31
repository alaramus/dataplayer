"""Put sample files into a user's personal directory, and tidy up after tests.

A development tool, not part of the API: a fresh directory is empty, so there
would be nothing to look at or to run an end-to-end scenario against. It also
removes the directories of users that no longer exist, which is what the test
suite leaves behind every time it empties the shared development database.

    python -m app.seed_storage [email]
"""

import asyncio
import base64
import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.users import crud, storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# More than one page of the default size, so paging is exercised.
SAMPLE_ROWS = 250

# One real 1×1 PNG: the viewer verifies bytes, so a signature followed by
# sample text would advertise an image that correctly refuses to open.
SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


# Every block the rendered representation knows, in one document: the
# remote image at the end is there to show that it is blocked, not fetched.
SAMPLE_MARKDOWN = r"""# Sample document

This file exists so the rendered Markdown representation has something
to show. Its source is one click away in the editor.

```summary
Every block this viewer knows, in one file, so a change to any of them has
somewhere to be seen.
```

```decision
Decision: Keep documents portable Markdown
Reason: A callout is a fenced code block anywhere else, so nothing is lost.
```

## What it renders

| Block | Comes from |
| --- | --- |
| Diagram | a `mermaid` fence |
| Chart | an `echarts` fence |
| Formula | KaTeX |

- [x] tables, lists and task lists
- [x] fenced code with the editor's own highlighting
- [x] a table of contents, search and export

The mass-energy equivalence is $E = mc^2$, and a block formula reads

$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

## A diagram

```mermaid
graph LR
  A[Catalog] --> B[Document]
  B --> C[Editor]
```

## A chart

```echarts
{
  "xAxis": { "type": "category", "data": ["Q1", "Q2", "Q3"] },
  "yAxis": { "type": "value" },
  "series": [{ "type": "bar", "data": [820, 932, 1200] }]
}
```

## A drawing

```svg
<svg viewBox="0 0 240 80" width="240" height="80" xmlns="http://www.w3.org/2000/svg">
  <circle cx="40" cy="40" r="24" fill="#6ea8fe"/>
  <circle cx="120" cy="40" r="24" fill="#c6f24e"/>
  <circle cx="200" cy="40" r="24" fill="#f78c6c"/>
</svg>
```

## Some code

```python
def total(rows: list[int]) -> int:
    return sum(rows)
```

A [relative link](notes.txt), a local image beside this document, and a remote
image, which is blocked:

![local logo](logo.png)

![remote](https://example.invalid/logo.png)
"""


def write_samples(home: Path) -> None:
    """Write examples for the native viewers and explicit table projections."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)

    rows = "\n".join(
        f"{index},city-{index},{index * 1000}" for index in range(1, SAMPLE_ROWS + 1)
    )
    (home / "sample.csv").write_text(
        f"id,name,population\n{rows}\n", encoding="utf-8"
    )
    (home / "sample.tsv").write_text(
        "id\tname\n1\tone\n2\ttwo\n", encoding="utf-8"
    )
    (home / "notes.txt").write_text(
        "\n".join(f"line {index}" for index in range(1, 21)) + "\n", encoding="utf-8"
    )
    # Structured content with a nested value and a number a float would round.
    # Its alternative table projection also has a key only a later record carries.
    people = [
        {"id": 1, "name": "Ann", "tags": ["reader"]},
        {"id": 2, "name": "Bo", "city": "Riga", "tags": []},
        {"id": 3, "name": "Cyd", "account": 10000000000000001},
    ]
    (home / "people.json").write_text(
        json.dumps(people, indent=2) + "\n", encoding="utf-8"
    )
    events = [
        {"at": f"2026-08-{day:02d}", "kind": "login", "ok": day % 2 == 0}
        for day in range(1, 6)
    ]
    (home / "events.jsonl").write_text(
        "".join(f"{json.dumps(event)}\n" for event in events), encoding="utf-8"
    )
    # Named .json and not JSON: its JSON viewer shows the source and says why.
    (home / "broken.json").write_text('{"a": 1,\n "b" 2}\n', encoding="utf-8")
    (home / "logo.png").write_bytes(SAMPLE_PNG)
    (home / "guide.md").write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    _write_dataset_samples(home)

    reports = home / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "q3.csv").write_text("quarter,revenue\nQ3,1200\n", encoding="utf-8")
    (home / "empty").mkdir(exist_ok=True)


def _write_dataset_samples(home: Path) -> None:
    """A columnar file and a workbook, for the datasets of D51.

    Written here rather than committed as fixtures so the samples stay honest
    about the libraries that read them, and so nothing binary lives in the
    repository. This is the one place outside the file adapter that touches
    either library, and it is a development tool rather than the application.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from openpyxl import Workbook

    table = pa.table(
        {
            "id": pa.array(range(1, SAMPLE_ROWS + 1), type=pa.int64()),
            "city": pa.array([f"city-{index}" for index in range(1, SAMPLE_ROWS + 1)]),
            "population": pa.array(
                [index * 1000.5 for index in range(1, SAMPLE_ROWS + 1)],
                type=pa.float64(),
            ),
            "capital": pa.array([index % 7 == 0 for index in range(1, SAMPLE_ROWS + 1)]),
            "tags": pa.array(
                [["north"] if index % 2 else ["south", "coast"] for index in range(1, SAMPLE_ROWS + 1)],
                type=pa.list_(pa.string()),
            ),
        }
    )
    # Several row groups on purpose: a page then begins inside one of them.
    pq.write_table(table, home / "cities.parquet", row_group_size=100)

    book = Workbook()
    revenue = book.active
    if revenue is None:  # pragma: no cover - a new workbook always has one sheet
        raise RuntimeError("A new workbook has no active sheet")
    revenue.title = "Revenue"
    revenue.append(["quarter", "amount", "closed"])
    for quarter, amount in (("Q1", 820), ("Q2", 932), ("Q3", 1200), ("Q4", 1310)):
        revenue.append([quarter, amount, quarter != "Q4"])
    people = book.create_sheet("People")
    people.append(["name", "started"])
    people.append(["Ann", datetime(2026, 1, 14, tzinfo=UTC).date()])
    people.append(["Bo", datetime(2026, 3, 2, tzinfo=UTC).date()])
    hidden = book.create_sheet("Working notes")
    hidden.append(["note"])
    hidden.append(["not for the report"])
    hidden.sheet_state = "hidden"
    book.save(home / "budget.xlsx")


def remove_orphan_homes(*, keep: set[uuid.UUID]) -> list[uuid.UUID]:
    """Delete the home directories of users that no longer exist.

    The test suite shares the development database and empties the user table,
    so every run strands a full directory under an id nobody can log in as.

    This decides *which* homes go; `storage.remove_home` is what takes one
    away, so where a home lives and how it is removed keep one definition. Only
    a real directory named after a user id is a candidate: anything else under
    the root was put there for a reason this script does not know, and guessing
    about it is the one destructive mistake it could make.
    """
    root = settings.USER_STORAGE_ROOT
    if not root.is_dir():
        return []

    removed: list[uuid.UUID] = []
    for entry in sorted(root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            logger.info("Not a home directory, left alone: %s", entry.name)
            continue
        try:
            user_id = uuid.UUID(entry.name)
        except ValueError:
            logger.info("Name is not a user id, left alone: %s", entry.name)
            continue
        if user_id in keep:
            continue
        storage.remove_home(user_id)
        removed.append(user_id)
        logger.info("Removed the home of a user that no longer exists: %s", entry.name)
    return removed


async def main(email: str) -> None:
    async with async_session_maker() as session:
        user = await crud.get_user_by_email(session=session, email=email)
        live_ids = await crud.get_all_user_ids(session=session)
    if user is None:
        logger.error("No such user: %s", email)
        raise SystemExit(1)

    removed = remove_orphan_homes(keep=live_ids)
    logger.info("Removed %d orphaned home directories", len(removed))

    home = storage.home_dir(user.id)
    write_samples(home)
    logger.info("Sample files written to %s", home)


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else settings.FIRST_SUPERUSER
    asyncio.run(main(address), loop_factory=loop_factory)
