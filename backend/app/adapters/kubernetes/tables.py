"""A kind's objects as the cluster's own table, and an object's pages (D465, D466).

A list is read whole in pages of `PAGE` by the API's `limit` and `continue`,
at most `MOST` objects, asked as a `Table` so its columns are the ones
`kubectl get` prints for built-in and custom kinds alike. Filters and sorts
are applied here (D2d). The server's "Age" is replaced by the creation time,
which sorts.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, PageCommand
from app.adapters.kubernetes.discovery import Resource
from app.adapters.kubernetes.session import TABLE, Forbidden, KubernetesSession, segment
from app.adapters.listed import column, listed_column, listed_page
from app.adapters.relation import TypeCategory
from app.core.translation import say

type Row = list[str | None]

PAGE = 500
MOST = 10_000
# How far back a container's logs reach, and how long a line may be.
LOG_DEPTH = 10_000
LINE_BYTES = 16 * 1024
LOG_BYTES = 16 * 1024 * 1024
EVENTS_SHOWN = 2_000

_COMMANDS: list[PageCommand] = ["download", "chart", "share"]
_CATEGORIES: dict[str, TypeCategory] = {
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "date": "datetime",
}
NAMESPACE_COLUMN = "Namespace"
CREATED_COLUMN = "Created"

EVENT_COLUMNS = [
    listed_column("Last seen", "datetime", nullable=True),
    listed_column("Type", "string"),
    listed_column("Reason", "string", nullable=True),
    listed_column("Object", "string"),
    listed_column("Message", "string", nullable=True),
    listed_column("Count", "number", nullable=True),
    listed_column("Namespace", "string", nullable=True),
]
LOG_COLUMNS = [column("time", "datetime", nullable=True), column("text", "string")]


@dataclass
class Listed:
    """A kind's table as read: the server's columns and rows, and whether cut."""

    columns: list[FetchColumn]
    rows: list[Row]
    # Each row's name, namespace and creation, for catalog nodes and ids.
    names: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    summaries: list[str | None] = field(default_factory=list)
    cut: bool = False


def text_of(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def instant(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _summary(cells: list[Any], definitions: list[dict[str, Any]]) -> str | None:
    """The first two priority-0 columns after the name: "1/1 · Running"."""
    shown: list[str] = []
    for definition, cell in zip(definitions, cells, strict=False):
        if definition.get("priority", 0) != 0 or definition.get("format") == "name":
            continue
        if str(definition.get("name")) == "Age":
            continue
        text = text_of(cell)
        if text and text != "<none>":
            shown.append(text)
        if len(shown) == 2:
            break
    return " · ".join(shown) or None


def table_of(pages: list[dict[str, Any]], *, every_namespace: bool, cut: bool) -> Listed:
    definitions: list[dict[str, Any]] = []
    for answer in pages:
        found = answer.get("columnDefinitions")
        if isinstance(found, list) and found:
            definitions = [one for one in found if isinstance(one, dict)]
            break
    kept = [index for index, one in enumerate(definitions) if str(one.get("name")) != "Age"]
    columns: list[FetchColumn] = []
    if every_namespace:
        columns.append(listed_column(NAMESPACE_COLUMN, "string", nullable=True))
    seen = {NAMESPACE_COLUMN, CREATED_COLUMN}
    for index in kept:
        name = str(definitions[index].get("name") or f"column {index}")
        while name in seen:
            name += " "
        seen.add(name)
        category = _CATEGORIES.get(str(definitions[index].get("type")), "string")
        columns.append(listed_column(name, category, nullable=True))
    columns.append(listed_column(CREATED_COLUMN, "datetime", nullable=True))
    listed = Listed(columns=columns, rows=[], cut=cut)
    for answer in pages:
        for row in answer.get("rows") or []:
            if not isinstance(row, dict):
                continue
            found_cells = row.get("cells")
            cells: list[Any] = found_cells if isinstance(found_cells, list) else []
            metadata = (row.get("object") or {}).get("metadata") or {}
            name = str(metadata.get("name") or (cells[0] if cells else ""))
            namespace = metadata.get("namespace")
            created = metadata.get("creationTimestamp")
            values: Row = []
            if every_namespace:
                values.append(str(namespace) if namespace else None)
            values.extend(text_of(cells[index]) if index < len(cells) else None for index in kept)
            values.append(str(created) if created else None)
            listed.rows.append(values)
            listed.names.append((name, str(namespace) if namespace else None, str(created) if created else None))
            listed.summaries.append(_summary(cells, definitions))
    return listed


async def read_table(
    session: KubernetesSession,
    resource: Resource,
    namespace: str | None,
    *,
    selector: str | None = None,
    node_id: str = "",
) -> Listed:
    """Every object of a kind, page by page, as the server's table."""
    pages: list[dict[str, Any]] = []
    token = ""
    count = 0
    cut = False
    while True:
        params: dict[str, str | int] = {"limit": PAGE}
        if token:
            params["continue"] = token
        if selector:
            params["labelSelector"] = selector
        answer = await session.get(
            resource.base(namespace), params, asked=resource.asked("list"), node_id=node_id, accept=TABLE
        )
        if not isinstance(answer, dict):
            break
        pages.append(answer)
        count += len(answer.get("rows") or [])
        token = str((answer.get("metadata") or {}).get("continue") or "")
        if not token:
            break
        if count >= MOST:
            cut = True
            break
    listed = table_of(pages, every_namespace=resource.namespaced and namespace is None, cut=cut)
    if cut:
        del listed.rows[MOST:], listed.names[MOST:], listed.summaries[MOST:]
    return listed


def page(
    request: FetchRequest,
    columns: list[FetchColumn],
    rows: list[Row],
    *,
    notice: str | None = None,
    narrowed: bool = True,
    refresh_seconds: int | None = None,
) -> FetchResult:
    if narrowed:
        rows = listed_page(columns, rows, request.filters, request.sort)
    end = request.offset + request.limit
    reason = notice or say("What the cluster says is read here, not changed")
    return FetchResult(
        columns=columns,
        rows=rows[request.offset : end],
        has_more=len(rows) > end,
        update_reason=reason,
        insert_reason=reason,
        delete_reason=reason,
        record_supported=False,
        record_reason=reason,
        refresh_seconds=refresh_seconds,
        page_commands=list(_COMMANDS),
    )


def cut_notice(listed: Listed) -> str | None:
    if not listed.cut:
        return None
    return say("Only the first {count} are read", count=MOST)


def selector_of(spec: Any) -> str | None:
    """A label selector as the API's query takes it, from a `LabelSelector` or
    a Service's plain map; None for one that picks nothing.

    Keys and values come from the cluster, which validated them as labels;
    they are passed as one query parameter, never into a path.
    """
    if not isinstance(spec, dict):
        return None
    if "matchLabels" not in spec and "matchExpressions" not in spec:
        plain = {str(key): str(value) for key, value in spec.items()}
        return ",".join(f"{key}={value}" for key, value in sorted(plain.items())) or None
    terms = [f"{key}={value}" for key, value in sorted((spec.get("matchLabels") or {}).items())]
    for expression in spec.get("matchExpressions") or []:
        if not isinstance(expression, dict):
            continue
        key = str(expression.get("key") or "")
        values = ",".join(str(value) for value in expression.get("values") or [])
        operator = expression.get("operator")
        if operator == "In":
            terms.append(f"{key} in ({values})")
        elif operator == "NotIn":
            terms.append(f"{key} notin ({values})")
        elif operator == "Exists":
            terms.append(key)
        elif operator == "DoesNotExist":
            terms.append(f"!{key}")
    return ",".join(terms) or None


def pod_selector(body: dict[str, Any]) -> str | None:
    """Whom a workload's or a Service's `spec.selector` picks; the two shapes
    are told apart by `selector_of`."""
    return selector_of((body.get("spec") or {}).get("selector"))


def event_rows(answer: Any) -> list[Row]:
    rows: list[tuple[str, Row]] = []
    for event in (answer.get("items") if isinstance(answer, dict) else None) or []:
        if not isinstance(event, dict):
            continue
        involved = event.get("involvedObject") or {}
        last = (
            event.get("lastTimestamp")
            or event.get("eventTime")
            or (event.get("metadata") or {}).get("creationTimestamp")
        )
        rows.append(
            (
                str(last or ""),
                [
                    str(last) if last else None,
                    str(event.get("type") or "Normal"),
                    text_of(event.get("reason")),
                    f"{involved.get('kind', '')}/{involved.get('name', '')}",
                    text_of(event.get("message")),
                    text_of(event.get("count")),
                    text_of(involved.get("namespace") or (event.get("metadata") or {}).get("namespace")),
                ],
            )
        )
    rows.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in rows[:EVENTS_SHOWN]]


async def read_events(
    session: KubernetesSession, namespace: str | None, selector: str | None = None
) -> list[Row]:
    path = "/api/v1/events" if not namespace else f"/api/v1/namespaces/{segment(namespace)}/events"
    params: dict[str, str | int] = {"limit": MOST}
    if selector:
        params["fieldSelector"] = selector
    answer = await session.get(path, params, asked=Forbidden("list", "events"))
    return event_rows(answer)


def log_rows(text: str) -> list[Row]:
    """`timestamps=true` lines, newest first, each cut at `LINE_BYTES`."""
    rows: list[Row] = []
    for line in text.splitlines():
        stamp, space, rest = line.partition(" ")
        moment = instant(stamp) if space else None
        body = rest if moment is not None else line
        if len(body.encode()) > LINE_BYTES:
            body = body.encode()[:LINE_BYTES].decode(errors="ignore") + " …"
        rows.append([stamp if moment is not None else None, body])
    rows.reverse()
    return rows
