"""The indexes and constraints of a MySQL table (D37–D40).

Names are the server's: `ALTER TABLE … ADD INDEX (…)` and `ADD UNIQUE (…)`
name what they make from its first column, and a foreign key is named
`<table>_ibfk_<n>`. What was made is found by reading the table again.

A unique key and a unique index are one thing in MySQL, so a unique
constraint is dropped as the index it is, and an index that is a unique
constraint is dropped through the constraint, as PostgreSQL's is.
"""

from app.adapters.constraints import (
    ConstraintCreated,
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
    RepeatingValues,
    UniqueConstraintSpec,
    UnmatchedRows,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
    IndexDropped,
)
from app.adapters.mysql.columns import bounded_count
from app.adapters.mysql.inspection import RelationFacts
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.mysql.vocabulary import INDEX_METHODS, is_text
from app.adapters.relation import RefAction
from app.core.translation import N_, say

REF_ACTION_SQL: dict[RefAction, str] = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
}

KEY_REFUSALS: dict[int, str] = {
    1062: N_("Some values repeat, so a unique key cannot be built"),
    1170: N_("A text or blob column in a key needs a length; use Text rather than Long text"),
    3152: N_("A JSON column cannot be part of a key"),
    1214: N_("This table's engine cannot build that kind of index"),
    1252: N_("A spatial index needs a geometry column that requires a value"),
    1687: N_("A spatial index needs a geometry column that requires a value"),
    1553: N_("A foreign key needs this index"),
    1215: N_("These columns and the ones they point at cannot be compared"),
    3780: N_("These columns and the ones they point at cannot be compared"),
    6125: N_("The target relation has no unique key over those columns"),
    1822: N_("The target relation has no unique key over those columns"),
    1452: N_("Some rows point at nothing in the target relation"),
    1826: N_("A constraint of that name already exists"),
    1061: N_("An index of that name already exists"),
}


def _names(columns: list[str]) -> Composable:
    return SQL(", ").join(Identifier(name) for name in columns)


class MysqlKeys:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id)
        reason = self._relation.structure_reason(facts)
        if reason is not None:
            raise ValueError(reason)
        return facts

    @staticmethod
    def _check_columns(facts: RelationFacts, columns: list[str]) -> None:
        known = {column.name for column in facts.columns}
        for name in columns:
            if name not in known:
                raise ValueError(say('Relation has no column "{column}"', column=name))

    async def _alter(self, facts: RelationFacts, action: Composable) -> None:
        statement = SQL("ALTER TABLE {} ").format(Identifier(facts.schema, facts.name)) + action
        async with self._session.altering(refusals=KEY_REFUSALS) as work:
            await work.execute(statement.text())

    async def _repeating(self, facts: RelationFacts, columns: list[str]) -> tuple[int, bool]:
        """Values that appear more than once; a row with a NULL repeats nothing."""
        body = SQL("SELECT 1 FROM {} WHERE {} GROUP BY {} HAVING COUNT(*) > 1").format(
            Identifier(facts.schema, facts.name),
            SQL(" AND ").join(SQL("{} IS NOT NULL").format(Identifier(name)) for name in columns),
            _names(columns),
        )
        return await bounded_count(self._session, body)

    # --- Indexes ----------------------------------------------------------

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts = await self._table(request.node_id)
        self._check_columns(facts, request.columns)
        method = INDEX_METHODS.get(request.method)
        if method is None:
            raise ValueError(say('Unknown index method "{method}"', method=request.method))
        if request.unique and not method.unique_supported:
            raise ValueError(say("{title} cannot build a unique index", title=say(method.title)))
        if len(request.columns) > 1 and not method.multi_column_supported:
            raise ValueError(say("{title} cannot index more than one column", title=say(method.title)))
        types = {column.name: column.type for column in facts.columns}
        if method.code == "fulltext" and not all(is_text(types[name].sql) for name in request.columns):
            raise ValueError(say("A full text index covers text columns only"))
        if method.code == "spatial" and types[request.columns[0]].category != "geometric":
            raise ValueError(say("A spatial index covers a geometry column only"))
        if request.unique:
            groups, exact = await self._repeating(facts, request.columns)
            if groups:
                return IndexBlocked(duplicate_groups=groups, exact=exact)
        before = {index.name for index in facts.indexes}
        kind = "UNIQUE " if request.unique else {"fulltext": "FULLTEXT ", "spatial": "SPATIAL "}.get(method.code, "")
        await self._alter(facts, SQL("ADD " + kind + "INDEX ({})").format(_names(request.columns)))
        after = await self._relation.facts(request.node_id)
        made = sorted(index.name for index in after.indexes if index.name not in before)
        return IndexCreated(name=made[0] if made else "")

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts = await self._table(request.node_id)
        index = next((item for item in facts.indexes if item.name == request.name), None)
        if index is None:
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        if index.name == "PRIMARY":
            raise ValueError(say('Index "{name}" belongs to the primary key; drop that instead', name=index.name))
        if any(key.kind == "UNIQUE" and key.name == index.name for key in facts.keys):
            raise ValueError(
                say(
                    'Index "{name}" belongs to constraint "{constraint}"; drop that instead',
                    name=index.name,
                    constraint=index.name,
                )
            )
        await self._alter(facts, SQL("DROP INDEX {}").format(Identifier(index.name)))
        return IndexDropped(name=index.name)

    # --- Constraints ------------------------------------------------------

    async def create_constraint(self, request: CreateConstraintRequest) -> CreateConstraintResult:
        facts = await self._table(request.node_id)
        spec = request.constraint
        self._check_columns(facts, spec.columns)
        before = {key.name for key in facts.keys} | {check.name for check in facts.checks}
        if isinstance(spec, UniqueConstraintSpec):
            groups, exact = await self._repeating(facts, spec.columns)
            if groups:
                return RepeatingValues(groups=groups, exact=exact)
            action: Composable = SQL("ADD UNIQUE ({})").format(_names(spec.columns))
        else:
            if spec.on_update == "set_default" or spec.on_delete == "set_default":
                raise ValueError(say("InnoDB does not carry out SET DEFAULT on a foreign key"))
            target = await self._relation.facts(spec.target_node_id)
            if not any(
                key.kind in ("PRIMARY KEY", "UNIQUE") and key.columns == spec.target_columns
                for key in target.keys
            ):
                raise ValueError(
                    say(
                        '"{schema}.{name}" has no unique key over those columns',
                        schema=target.schema,
                        name=target.name,
                    )
                )
            rows, exact = await self._unmatched(facts, spec.columns, target, spec.target_columns)
            if rows:
                return UnmatchedRows(rows=rows, exact=exact)
            action = SQL(
                "ADD FOREIGN KEY ({}) REFERENCES {} ({}) ON UPDATE "
                + REF_ACTION_SQL[spec.on_update]
                + " ON DELETE "
                + REF_ACTION_SQL[spec.on_delete]
            ).format(
                _names(spec.columns),
                Identifier(target.schema, target.name),
                _names(spec.target_columns),
            )
        await self._alter(facts, action)
        after = await self._relation.facts(request.node_id)
        made = sorted(
            name
            for name in {key.name for key in after.keys} | {check.name for check in after.checks}
            if name not in before
        )
        return ConstraintCreated(name=made[0] if made else "")

    async def _unmatched(
        self, facts: RelationFacts, columns: list[str], target: RelationFacts, target_columns: list[str]
    ) -> tuple[int, bool]:
        """Rows whose key names no row of the target; a NULL anywhere names none."""
        body = SQL("SELECT 1 FROM {} AS dp_source WHERE {} AND NOT EXISTS (SELECT 1 FROM {} AS dp_target WHERE {})").format(
            Identifier(facts.schema, facts.name),
            SQL(" AND ").join(SQL("dp_source.{} IS NOT NULL").format(Identifier(name)) for name in columns),
            Identifier(target.schema, target.name),
            SQL(" AND ").join(
                SQL("dp_target.{} = dp_source.{}").format(Identifier(there), Identifier(here))
                for here, there in zip(columns, target_columns, strict=True)
            ),
        )
        return await bounded_count(self._session, body)

    async def drop_constraint(self, request: DropConstraintRequest) -> ConstraintDropped:
        facts = await self._table(request.node_id)
        key = next((item for item in facts.keys if item.name == request.name), None)
        check = next((item for item in facts.checks if item.name == request.name), None)
        if key is None and check is None:
            raise ValueError(say('Relation has no constraint "{name}"', name=request.name))
        if key is not None and key.kind == "PRIMARY KEY":
            raise ValueError(
                say("A primary key cannot be dropped here: rows can only be edited while one exists")
            )
        name = Identifier(request.name)
        if key is not None and key.kind == "UNIQUE":
            action: Composable = SQL("DROP INDEX {}").format(name)
        elif key is not None:
            action = SQL("DROP FOREIGN KEY {}").format(name)
        elif (await self._session.profile()).mariadb:
            action = SQL("DROP CONSTRAINT {}").format(name)
        else:
            action = SQL("DROP CHECK {}").format(name)
        await self._alter(facts, action)
        return ConstraintDropped(name=request.name)

