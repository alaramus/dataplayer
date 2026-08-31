from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, assert_never
from uuid import UUID

from psycopg import sql

from app.adapters.cells import encode_cell
from app.adapters.fetch import (
    FetchColumn,
    FetchReference,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
)
from app.adapters.postgres.catalog import is_system_schema
from app.adapters.postgres.column_type import build_column_type
from app.adapters.postgres.row_handle import encode_row_handle
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import (
    SECTION_ID,
    SystemReport,
    report_for,
)
from app.adapters.protocol import AdapterError
from app.adapters.relation import ColumnType

# Every operator maps to a fixed SQL fragment. Nothing here is ever built from
# client input: the client chooses an operator from a closed set, and that is
# the whole of its influence on the shape of the statement.
_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# Foreign keys of one relation, in key order, with the relation they point at.
# `confrelid` is an oid, so a target renamed since the constraint was written
# still answers with the name it has now.
_REFERENCES = """
SELECT con.conname AS name,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = u.attnum
       ) AS column_names,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.confrelid AND att.attnum = u.attnum
       ) AS target_column_names,
       fn.nspname AS target_schema,
       fc.relname AS target_relation
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_class fc ON fc.oid = con.confrelid
JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE n.nspname = %s AND c.relname = %s AND con.contype = 'f'
ORDER BY con.conname
"""

_ORDERED = frozenset({"number", "string", "boolean", "datetime", "uuid", "enum"})
_COMPARED = frozenset({"number", "string", "datetime"})
_EQUAL = frozenset({"number", "string", "datetime", "boolean", "uuid", "enum"})
_SERVER_TEXT = frozenset({"array", "geometric", "json", "range", "composite", "other"})


@dataclass(frozen=True)
class RelationReference:
    """One foreign key, with both ends of it.

    The pair of column lists is what makes following a key the source's own
    work: nothing outside this package ever sees which of the target's columns
    a local one stands for, so nothing outside can pair them up wrongly.
    """

    name: str
    columns: list[str]
    target_node_id: str
    target_columns: list[str]


@dataclass(frozen=True)
class RelationFetchInfo:
    columns: list[FetchColumn]
    primary_key: list[str]
    # How a row is named. The key where there is one, because a physical
    # position is invalidated wholesale by anything that rewrites the table;
    # its place where there is not, because that is better than refusing to
    # edit a table that is perfectly editable (D42).
    row_identity: Literal["primary_key", "physical", "none"]
    update_supported: bool
    update_reason: str | None
    insert_supported: bool
    insert_reason: str | None
    delete_supported: bool
    delete_reason: str | None


@dataclass(frozen=True)
class PreparedRead:
    """One validated read shared by the page and export capabilities.

    `source` is what the statement selects from — a relation, or a report's own
    statement wrapped as a subquery (D55) — so neither builder below has to ask
    which of the two it is holding. `relation` names the relation when there is
    one, for the questions only a relation can answer.
    """

    source: sql.Composable
    relation: tuple[str, str] | None
    info: RelationFetchInfo
    request: FetchRequest


# What a physical row identity is read and written as. Both are needed: on a
# partitioned parent two rows in different partitions share a ctid.
TABLEOID = "__dp_tableoid"
CTID = "__dp_ctid"


def _supports_filter_value_coercion(type_: ColumnType) -> bool:
    if type_.category == "datetime":
        return _is_supported_datetime_sql(type_.sql)
    return type_.category in _EQUAL


def _is_supported_datetime_sql(sql_type: str) -> bool:
    return (
        sql_type == "date"
        or sql_type.startswith("timestamp")
        or sql_type.startswith("time")
    )


def column_capabilities(type_: ColumnType) -> tuple[bool, list[FilterOp]]:
    operators: list[FilterOp] = []
    coercible = _supports_filter_value_coercion(type_)
    if coercible and type_.category in _EQUAL:
        operators.extend(["eq", "ne", "in"])
    if coercible and type_.category in _COMPARED:
        operators.extend(["gt", "gte", "lt", "lte"])
    if coercible and type_.category == "string":
        operators.extend(["contains", "starts_with"])
    operators.extend(["is_null", "is_not_null"])
    return coercible and type_.category in _ORDERED, operators


def coerce_filter_value(value: str, type_: ColumnType) -> object:
    """Turn the text boundary value into the driver's native parameter type."""
    try:
        match type_.category:
            case "number":
                return Decimal(value)
            case "boolean":
                if value == "true":
                    return True
                if value == "false":
                    return False
                raise ValueError
            case "uuid":
                return UUID(value)
            case "datetime":
                return _coerce_datetime(value, type_.sql)
            case "string" | "enum":
                return value
            case _:
                raise ValueError
    except (InvalidOperation, ValueError):
        raise ValueError from None


def _coerce_datetime(value: str, sql_type: str) -> date | datetime | time:
    if sql_type.startswith("timestamp"):
        return datetime.fromisoformat(value)
    if sql_type.startswith("time"):
        return time.fromisoformat(value)
    if sql_type == "date":
        return date.fromisoformat(value)
    raise ValueError


class PostgresFetch:
    """Reading rows out of a relation.

    Statements are assembled with psycopg.sql composition: identifiers through
    Identifier, values through placeholders. The old application formatted them
    into a template string and accepted a raw SQL fragment from the client,
    which is injection by construction.
    """

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        prepared = await self.prepare(request)
        info = prepared.info
        columns = info.columns

        # A report has no constraints to report: the columns of a join carry
        # none, and inventing one from a column name is the guessing D36
        # exists to avoid.
        references = [
            FetchReference(
                name=reference.name,
                columns=reference.columns,
                target_title=reference.target_node_id,
            )
            for reference in (
                []
                if prepared.relation is None
                else await self.references(*prepared.relation)
            )
        ]
        statement, params = self._build(
            prepared.source,
            columns,
            prepared.request,
            info,
        )
        rows = await self._session.query(statement.as_string(), tuple(params))

        # One row beyond the page tells us whether another page exists, without
        # a COUNT(*) on every request.
        has_more = len(rows) > request.limit
        page = rows[: request.limit]
        return FetchResult(
            columns=columns,
            rows=[
                [encode_cell(row[column.name], column.type) for column in columns]
                for row in page
            ],
            has_more=has_more,
            row_handles=[self._row_handle(row, info, columns) for row in page],
            references=references,
            update_supported=info.update_supported,
            update_reason=info.update_reason,
            insert_supported=info.insert_supported,
            insert_reason=info.insert_reason,
            delete_supported=info.delete_supported,
            delete_reason=info.delete_reason,
        )

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        """Validate the source and the query once for a page or an export."""
        source, relation, info = await self._read_source(request.node_id)
        known = {column.name: column for column in info.columns}
        self._reject_unknown_columns(request, known)
        filters = self._validate_filters(request.filters, known)
        self._reject_unsortable_columns(request, known)
        request = request.model_copy(update={"filters": filters})
        return PreparedRead(
            source=source, relation=relation, info=info, request=request
        )

    async def _read_source(
        self, node_id: str
    ) -> tuple[sql.Composable, tuple[str, str] | None, RelationFetchInfo]:
        """What a node id selects from, and what is known about its rows."""
        report = report_for(node_id)
        if report is not None:
            return (
                sql.SQL("({}) AS report").format(report.statement),
                None,
                await self._report_info(report),
            )
        # An id in the reports' own namespace that names no report is wrong
        # about the reports, not about a relation, and saying "expected
        # schema.table" about it would send the reader looking in the wrong
        # place.
        if node_id == SECTION_ID or node_id.startswith(f"{SECTION_ID}."):
            raise ValueError(f'"{node_id}" is not a report of this source')

        schema, _, table = node_id.partition(".")
        if not table:
            raise ValueError(f'"{node_id}" is not a relation: expected schema.table')
        return (
            sql.Identifier(schema, table),
            (schema, table),
            await self.relation_info(schema, table),
        )

    async def _report_info(self, report: SystemReport) -> RelationFetchInfo:
        """The columns of a report, described by the server that will run it.

        Nothing is written through a report and no row handle is issued: there
        is no row to name behind a subquery, which is the position D42 already
        leaves a view in.
        """
        described = await self._session.describe(
            sql.SQL("SELECT * FROM ({}) AS report LIMIT 0")
            .format(report.statement)
            .as_string()
        )
        types = await self._types_by_oid([oid for _, oid in described])
        columns: list[FetchColumn] = []
        for name, oid in described:
            type_ = build_column_type(types[oid])
            sortable, filter_operators = column_capabilities(type_)
            columns.append(
                FetchColumn(
                    name=name,
                    type=type_,
                    sortable=sortable,
                    filter_operators=filter_operators,
                )
            )
        refused = f'"{report.title}" is a report and holds no rows of its own'
        return RelationFetchInfo(
            columns=columns,
            primary_key=[],
            row_identity="none",
            update_supported=False,
            update_reason=refused,
            insert_supported=False,
            insert_reason=refused,
            delete_supported=False,
            delete_reason=refused,
        )

    async def _types_by_oid(self, oids: list[int]) -> dict[int, dict[str, Any]]:
        """The same type facts a relation's columns are built from, by OID."""
        rows = await self._session.query(
            """
            SELECT t.oid AS oid,
                   format_type(t.oid, NULL) AS sql_type,
                   t.typname AS type_name,
                   t.typcategory AS type_category,
                   format_type(t.typelem, NULL) AS element_sql,
                   et.typname AS element_name,
                   et.typcategory AS element_category
            FROM pg_type t
            LEFT JOIN pg_type et ON et.oid = t.typelem
            WHERE t.oid = ANY(%s)
            """,
            (sorted(set(oids)),),
        )
        return {int(row["oid"]): row for row in rows}

    def build_export(
        self, prepared: PreparedRead, requested_columns: list[str]
    ) -> tuple[sql.Composed, list[Any], list[FetchColumn]]:
        """Compose the unbounded SQL behind a server-side export cursor."""
        known = {column.name: column for column in prepared.info.columns}
        unknown = [name for name in requested_columns if name not in known]
        if unknown:
            raise ValueError(f'Unknown export column: "{unknown[0]}"')
        columns = [known[name] for name in requested_columns]
        params: list[Any] = []
        selected = sql.SQL(", ").join(select_expression(column) for column in columns)
        statement = sql.SQL("SELECT {} FROM {}").format(
            selected, prepared.source
        )
        conditions = [
            self._condition(filter_, params) for filter_ in prepared.request.filters
        ]
        if conditions:
            statement = (
                statement + sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)
            )
        ordering: list[sql.Composable] = [
            sql.SQL("{} {}").format(
                sql.Identifier(item.column),
                sql.SQL("DESC" if item.descending else "ASC"),
            )
            for item in prepared.request.sort
        ]
        ordering.extend(_tiebreak(prepared.info))
        if ordering:
            statement = (
                statement + sql.SQL(" ORDER BY ") + sql.SQL(", ").join(ordering)
            )
        return statement, params, columns

    @staticmethod
    def _row_handle(
        row: dict[str, Any], info: RelationFetchInfo, columns: list[FetchColumn]
    ) -> str | None:
        if not info.delete_supported:
            return None
        keys = row_identity_values(row, info, columns)
        if keys is None:
            return None
        return encode_row_handle(keys, str(row["__dp_xmin"]))

    @staticmethod
    def _reject_unknown_columns(
        request: FetchRequest, known: dict[str, FetchColumn]
    ) -> None:
        """Validate identifiers against the relation before building anything.

        This is what makes the composition below safe: by the time a name
        reaches Identifier it is known to be a real column.
        """
        used = [item.column for item in request.filters]
        used += [item.column for item in request.sort]
        for column in used:
            if column not in known:
                raise ValueError(f'Relation has no column "{column}"')

    @staticmethod
    def _validate_filters(
        filters: list[Filter], known: dict[str, FetchColumn]
    ) -> list[Filter]:
        validated: list[Filter] = []
        for filter_ in filters:
            column = known[filter_.column]
            if filter_.op not in column.filter_operators:
                raise ValueError(
                    f'Cannot filter column "{column.name}" with "{filter_.op}"'
                )
            match filter_:
                case ScalarFilter(value=value):
                    try:
                        coerced = coerce_filter_value(value, column.type)
                    except ValueError:
                        raise ValueError(
                            f'Invalid value for column "{column.name}"'
                        ) from None
                    validated.append(filter_.model_copy(update={"value": coerced}))
                case InFilter(values=values):
                    try:
                        coerced = [
                            coerce_filter_value(value, column.type) for value in values
                        ]
                    except ValueError:
                        raise ValueError(
                            f'Invalid value for column "{column.name}"'
                        ) from None
                    validated.append(filter_.model_copy(update={"values": coerced}))
                case NullFilter():
                    validated.append(filter_)
                case unreachable:
                    assert_never(unreachable)
        return validated

    @staticmethod
    def _reject_unsortable_columns(
        request: FetchRequest, known: dict[str, FetchColumn]
    ) -> None:
        for sort in request.sort:
            if not known[sort.column].sortable:
                raise ValueError(f'Cannot sort column "{sort.column}"')

    async def relation_info(self, schema: str, table: str) -> RelationFetchInfo:
        rows = await self._session.query(
            """
            SELECT a.attname AS name,
                   format_type(a.atttypid, a.atttypmod) AS sql_type,
                   a.atttypmod AS type_mod,
                   t.typcategory AS type_category,
                   t.typname AS type_name,
                   format_type(t.typelem, a.atttypmod) AS element_sql,
                   et.typcategory AS element_category,
                   et.typname AS element_name,
                   c.relkind AS relation_kind,
                   a.attgenerated AS generated,
                   a.attidentity AS identity,
                   (ad.adbin IS NOT NULL OR a.attidentity <> '') AS has_default,
                   NOT a.attnotnull AS nullable,
                   (SELECT array_agg(pa.attname ORDER BY key.ord)
                      FROM pg_index i
                      CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS key(attnum, ord)
                      JOIN pg_attribute pa
                        ON pa.attrelid = i.indrelid AND pa.attnum = key.attnum
                     WHERE i.indrelid = c.oid AND i.indisprimary) AS primary_key,
                   (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
                      FROM pg_enum e WHERE e.enumtypid = t.oid) AS enum_values,
                   (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
                      FROM pg_enum e WHERE e.enumtypid = et.oid) AS element_enum_values
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_type t ON t.oid = a.atttypid
            LEFT JOIN pg_type et ON et.oid = t.typelem
            LEFT JOIN pg_attrdef ad
              ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
            WHERE n.nspname = %s AND c.relname = %s
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (schema, table),
        )
        if not rows:
            raise AdapterError("config", f'Relation "{schema}.{table}" does not exist')
        primary_key = [str(value) for value in (rows[0]["primary_key"] or [])]
        table_kind = str(rows[0]["relation_kind"]) in {"r", "p"}
        # A key is not required to name a row any more: where there is none,
        # the row's own place plus its version says which row and which version
        # of it, which is all an optimistic edit ever needed (D42).
        # A view has neither: no key of its own and no ctid to fall back on,
        # which is why there is a third answer rather than a second.
        physical_kind = str(rows[0]["relation_kind"]) in {"r", "p", "m"}
        row_identity: Literal["primary_key", "physical", "none"] = (
            "primary_key"
            if primary_key
            else ("physical" if physical_kind else "none")
        )
        # A catalog of the server is an ordinary table by relkind, and on a
        # superuser connection PostgreSQL performs the write: renaming
        # pg_default in pg_tablespace succeeds. Refused here rather than
        # left to the driver, which is the same rule that already refuses a
        # new table in pg_catalog, now said for rows too (D54).
        server_owned = is_system_schema(schema)
        writable = table_kind and not server_owned
        owned = f'"{schema}" belongs to the server'

        def refusal(not_a_table: str) -> str | None:
            if writable:
                return None
            return owned if server_owned else not_a_table

        update_supported = writable
        update_reason = refusal("Only tables can be edited")
        insert_supported = writable
        insert_reason = refusal("Only tables accept inserted rows")
        delete_supported = writable
        delete_reason = refusal("Only tables can delete rows")
        columns: list[FetchColumn] = []
        for row in rows:
            type_ = build_column_type(row)
            sortable, filter_operators = column_capabilities(type_)
            columns.append(
                FetchColumn(
                    name=str(row["name"]),
                    type=type_,
                    sortable=sortable,
                    filter_operators=filter_operators,
                    editable=update_supported and str(row["generated"]) == "",
                    nullable=bool(row["nullable"]),
                    insertable=(
                        insert_supported
                        and str(row["generated"]) == ""
                        and str(row["identity"]) != "a"
                    ),
                    insert_required=(
                        insert_supported
                        and str(row["generated"]) == ""
                        and str(row["identity"]) != "a"
                        and not bool(row["nullable"])
                        and not bool(row["has_default"])
                    ),
                    has_default=bool(row["has_default"]),
                )
            )
        return RelationFetchInfo(
            columns=columns,
            primary_key=primary_key,
            row_identity=row_identity,
            update_supported=update_supported,
            update_reason=update_reason,
            insert_supported=insert_supported,
            insert_reason=insert_reason,
            delete_supported=delete_supported,
            delete_reason=delete_reason,
        )

    async def references(self, schema: str, table: str) -> list[RelationReference]:
        """The foreign keys of one relation, as the fetch result reports them.

        Read on every page rather than remembered: the answer is what the
        source says now, and a constraint added or dropped between two pages
        would otherwise leave the grid offering a way out that no longer
        exists. The read cache already keeps a whole page for a moment, which
        is where the cost of asking again belongs.

        A constraint whose two ends do not pair up column for column is left
        out rather than reported half-read: the pairing is the whole of what
        following it means, and PostgreSQL only produces such a row while the
        catalog is being changed underneath the query.
        """
        rows = await self._session.query(_REFERENCES, (schema, table))
        found: list[RelationReference] = []
        for row in rows:
            columns = [str(name) for name in (row["column_names"] or [])]
            targets = [str(name) for name in (row["target_column_names"] or [])]
            if len(columns) != len(targets) or not columns:
                continue
            found.append(
                RelationReference(
                    name=str(row["name"]),
                    columns=columns,
                    target_node_id=(
                        f'{row["target_schema"]}.{row["target_relation"]}'
                    ),
                    target_columns=targets,
                )
            )
        return found

    def _build(
        self,
        source: sql.Composable,
        columns: list[FetchColumn],
        request: FetchRequest,
        info: RelationFetchInfo,
    ) -> tuple[sql.Composed, list[Any]]:
        params: list[Any] = []
        selected = sql.SQL(", ").join(select_expression(column) for column in columns)
        if any(column.editable for column in columns):
            selected = selected + sql.SQL(", xmin::text AS __dp_xmin")
        if info.row_identity == "physical":
            selected = selected + sql.SQL(
                ", tableoid::text AS __dp_tableoid, ctid::text AS __dp_ctid"
            )
        statement = sql.SQL("SELECT {} FROM {}").format(selected, source)

        conditions = [self._condition(f, params) for f in request.filters]
        if conditions:
            statement = (
                statement + sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)
            )

        ordering: list[sql.Composable] = [
            sql.SQL("{} {}").format(
                sql.Identifier(item.column),
                sql.SQL("DESC" if item.descending else "ASC"),
            )
            for item in request.sort
        ]
        # Always, and after whatever the reader asked for. Without it the order
        # is the plan's, an edited row moves because MVCC writes a new version
        # elsewhere, and page two does not promise to omit page one (D42).
        ordering.extend(_tiebreak(info))
        # A relation with nothing to break ties by and no sort asked for gets
        # no ORDER BY at all, rather than an empty one.
        if ordering:
            statement = (
                statement + sql.SQL(" ORDER BY ") + sql.SQL(", ").join(ordering)
            )

        # limit + 1 so the extra row can answer has_more.
        statement = statement + sql.SQL(" LIMIT %s OFFSET %s")
        params.extend([request.limit + 1, request.offset])
        return statement, params

    @staticmethod
    def _condition(filter_: Filter, params: list[Any]) -> sql.Composed:
        match filter_:
            case NullFilter(column=name, op=op):
                keyword = "IS NULL" if op == "is_null" else "IS NOT NULL"
                return sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(keyword))
            case InFilter(column=name, values=values):
                params.append(list(values))
                return sql.SQL("{} = ANY(%s)").format(sql.Identifier(name))
            case ScalarFilter(column=name, op="contains", value=value):
                params.append(f"%{value}%")
                return sql.SQL("{}::text ILIKE %s").format(sql.Identifier(name))
            case ScalarFilter(column=name, op="starts_with", value=value):
                params.append(f"{value}%")
                return sql.SQL("{}::text ILIKE %s").format(sql.Identifier(name))
            case ScalarFilter(column=name, op=op, value=value):
                params.append(value)
                return sql.SQL("{} {} %s").format(
                    sql.Identifier(name), sql.SQL(_COMPARISONS[op])
                )
            case unreachable:
                assert_never(unreachable)


def row_identity_values(
    row: dict[str, Any], info: RelationFetchInfo, columns: list[FetchColumn]
) -> list[str] | None:
    """What goes into this row's handle, in the order the match expects."""
    if info.row_identity == "physical":
        return [str(row[TABLEOID]), str(row[CTID])]
    known = {column.name: column for column in columns}
    keys = [encode_cell(row[name], known[name].type) for name in info.primary_key]
    if any(value is None for value in keys):
        return None
    return [value for value in keys if value is not None]


def row_match(info: RelationFetchInfo) -> list[sql.Composable]:
    """The conditions that pick out one exact row, one placeholder each.

    In one place because three commands ask the same question — change a cell,
    change a block, delete a set — and a fourth would otherwise ask it a fourth
    way.
    """
    if info.row_identity == "physical":
        return [sql.SQL("tableoid = %s::oid"), sql.SQL("ctid = %s::tid")]
    return [sql.SQL("{} = %s").format(sql.Identifier(name)) for name in info.primary_key]


def _tiebreak(info: RelationFetchInfo) -> list[sql.Composable]:
    """What settles the order once the reader's own sort has had its say.

    A relation with neither a key nor a place of its own — a view — gets
    nothing, because there is nothing honest to add. Its pages are as stable as
    its own definition makes them.
    """
    if info.row_identity == "physical":
        return [sql.SQL("tableoid"), sql.SQL("ctid")]
    return [sql.SQL("{} ASC").format(sql.Identifier(name)) for name in info.primary_key]


def select_expression(column: FetchColumn) -> sql.Composed:
    identifier = sql.Identifier(column.name)
    if column.type.category in _SERVER_TEXT:
        return sql.SQL("{}::text AS {}").format(identifier, identifier)
    return sql.SQL("{}").format(identifier)
