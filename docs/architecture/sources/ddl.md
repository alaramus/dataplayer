# Changing the structure of a relation

For adding, altering or removing a column, an index or a constraint, and for
renaming a node. Reading and changing rows is [relations.md](relations.md).

Four of these commands can be stopped by the data rather than by the request.
`postgres/counting.py` holds the one bounded count and whether it is the whole
truth, and D37, D38, D39 and D40 all go through it. A blocked answer is a 200 of its own
kind beside the changed one, discriminated by `kind`, for the reason
[D2d](contract.md) gives; a request that is wrong about the relation rather than
about its rows stays 422.

Decisions here: D27, D29, D30, D37, D38, D39, D40, D32, D117.

## D27. The source owns the column type vocabulary

A type must become syntax rather than a bound value, so the vocabulary is closed
and the mapping from code to fragment lives in the source. This preserves
[D2c](contract.md).

- Adding and dropping columns are independent capabilities. Relation metadata
  states whether this exact relation supports them, why not, and the
  source-owned `ColumnTypeOption` vocabulary.
- PostgreSQL permits ordinary and partitioned parent tables; views are not
  tables, and a child partition directs the user to its parent.
- An add request carries a column name, an opaque type code and nullability. The
  code is never SQL: PostgreSQL validates it against a closed registry and maps
  it to a fixed `psycopg.sql.SQL` fragment.
- Relation and column names always go through `Identifier`; metadata is reread
  before DDL to reject a duplicate or unknown column, and PostgreSQL's 63-byte
  identifier ceiling is checked before the server can silently truncate a name.
- Drop names exactly one current column and uses the default `RESTRICT`, never
  an implicit `CASCADE`. Indexes and constraints owned by that column go with
  it, which the destructive confirmation says; dependencies outside the table
  block the operation.
- Both commands invalidate the relation model and every open row query for the
  connector.

Known deviations:

- **The first type vocabulary is deliberately small.** Common scalar PostgreSQL
  types, without length, precision, arrays, domains or user-defined types.
  Expanding it needs typed option parameters, not a raw SQL escape hatch.
- **Add has no inline default.** A non-null column can therefore be added only
  where existing rows permit it. A literal default is assigned afterwards
  through D30.

Spec: [Adding and dropping columns](../../decisions/2026-08-27-column-add-drop-design.md)

## D29. A renamed column keeps its identity

Rename is its own capability, not add followed by drop, because the column keeps
its data and PostgreSQL keeps its dependencies.

- The request names one current column and one new name; fresh metadata rejects
  a missing source, a duplicate target and an unchanged name.
- Both identifiers go through the driver's composer, and the 63-byte ceiling is
  checked before the server can truncate the target silently.
- `ALTER TABLE … RENAME COLUMN … TO …` without `CASCADE`. PostgreSQL updates
  constraints, indexes and other catalog dependencies that refer to the
  identity; objects whose own exposed name is independent, such as a view
  output, keep theirs.
- Structure and rows are both invalidated: both cached projections name the old
  column.

Spec: [Column rename](../../decisions/2026-08-28-column-rename-design.md)

## D30. An entered default is a literal, never an expression

The text crosses the boundary as data, not SQL, which deliberately makes
functions and casts impossible to enter through the form.

- Two closed actions: set one text value, or drop the default.
- PostgreSQL quotes the text as a literal and asks the target column type to
  coerce it; an invalid value is rejected without storing anything. Empty
  strings and quotes survive.
- Generated columns are rejected explicitly.
- Metadata and rows are both invalidated afterwards: metadata exposes the new
  expression, and inserts may now produce different rows when the column is
  omitted.

Known deviations:

- **Source expressions are not supported.** `now()` is stored as the literal text
  `now()` where the column type accepts text. Expressions need a separate,
  source-owned vocabulary rather than a raw SQL field.

Spec: [Column default](../../decisions/2026-08-28-column-default-design.md)

## D37. Nullability counts the rows in the way

Requiring a value is a question about the rows, so the source asks it before
taking a lock rather than issuing DDL that would fail and relaying a driver
message that names row data.

- The request names one relation, one column and the state asked for.
- Before any lock, the source counts the rows holding no value and answers
  `NullabilityBlocked` with that count. The count stops at 1000 and reports
  whether it stopped.
- The count is not what makes the change safe — PostgreSQL's verification scan
  under `ACCESS EXCLUSIVE` is still the authority, and a row that gains a null in
  between comes back as the ordinary safe rejection. It is what makes the refusal
  useful.
- Allowing no value is a question about the shape, which is already in the
  relation model read to validate the request: a key column and an identity
  column always have a value and are named as such rather than sent to the
  server to be refused. Everything else, including a partitioned parent whose
  partition still requires the value, is left to PostgreSQL.
- A `changed` answer invalidates the relation model and the connector's row
  queries; a `blocked` answer changed nothing and invalidates nothing.

Known deviations:

- **Empty rows are not offered a value.** Filling them is a change to every row
  and belongs to a data round with its own confirmation, under D30's
  literal-value rule.
- **The verification scan is never skipped.** `NOT VALID` and a later adoption is
  how large tables get a `NOT NULL` without a long exclusive lock; that needs a
  vocabulary for a two-step constraint.
- **One column at a time.** A relation-wide edit would need a partial-failure
  answer, and there is no shape for one.

Spec: [Changing whether a column may be empty](../../decisions/2026-08-30-column-nullability-design.md)

## D38. The source composes a type change

It adds no vocabulary: the target is a code from the `ColumnTypeOption` list D27
already publishes, and `USING` is written by the source. A `USING` field would be
a general-purpose SQL channel — but it is written, because without it PostgreSQL
uses assignment casts only and the commonest change fails with advice to supply
exactly that expression.

- The statement is always `ALTER COLUMN … TYPE <target> USING <column>::<target>`,
  the column through `Identifier` and the target from the closed registry.
- Whether a conversion exists at all is asked of PostgreSQL:
  `SELECT <column>::<target> FROM <relation> WHERE false` reads no row, takes no
  lock and fails at parse time when there is no pathway.
- Whether the rows can be read as the target is answered by `pg_input_is_valid`
  when the column is a string type, which is when the conversion is PostgreSQL's
  own input function; the source then counts the failing rows, bounded as in
  D37. Where the conversion is a cast function there is no non-throwing way to
  try it, so no count is offered.
- Everything that only surfaces from the attempt — a default that cannot be cast,
  a view or rule on the column, a value out of range — is reduced to a sentence
  by SQLSTATE rather than by driver text, which quotes the data.
- Nothing dependent is dropped to make the change possible, the rule D27 set for
  `DROP COLUMN`. PostgreSQL rebuilds indexes and revalidates checks itself; a
  default that blocks the change is removed by the user with D30.

Known deviations:

- **A lossy conversion is not distinguished from a lossless one.** `numeric` to
  `integer` rounds silently. The screen says once that a type change rewrites
  every value and can lose information; a per-pair classification would be a
  second implementation of PostgreSQL's cast semantics.
- **A count exists only for string columns.** PostgreSQL has no `TRY_CAST`, and
  running the conversion to find out would mean doing the thing being asked
  about.
- **The target vocabulary carries no parameters.** No `varchar(n)`,
  `numeric(p,s)`, arrays, enums or domains.
- **SQLite changes structure by rebuilding the table** from its own text,
  edited, since its ALTER TABLE does little more than add and rename (D255).
- **ClickHouse counts before a type or nullability change, and undoes a failed
  one.** Its conversion is a mutation after the metadata has changed, and a
  failed mutation leaves the table unreadable, so the change is refused while
  any value would stop it (D273).
- **MySQL counts after the change is refused, for every source type.** It has
  no TRY_CAST either; the refused `MODIFY` is followed by a count of what the
  new type refuses (D235).

Spec: [Changing a column's type](../../decisions/2026-08-30-column-type-change-design.md)

## D39. The source names an index

Creating and dropping is one capability rather than two: a source that could make
an index and not unmake it would let a user build something they cannot remove.

- The gate is its own — a view cannot be indexed and a materialized view can — so
  `RelationModel` carries `index_changes_supported` and its reason.
- The request carries columns of this relation in index order, a method code and
  whether the index is unique, and nothing else. A name is deliberately absent:
  an index has no meaning to a user beyond the columns it covers, and PostgreSQL
  derives one and uniquifies it against the schema.
- `CREATE INDEX` reports nothing, so the answer names the index by reading the
  relation again and taking the one that was not there before whose columns,
  method and uniqueness match.
- A predicate, an expression, an operator class, sort or nulls ordering and
  `INCLUDE` are all out: the first two are the expressions [D2c](contract.md)
  refuses, the rest need a vocabulary of their own.
- The offered methods are a closed registry, but their limits are not restated
  here: `pg_indexam_has_property` answers `can_unique` and `can_multi_col`, and
  both travel with each method. Whether a method suits a column's type is left to
  the server, because it depends on installed operator classes.
- A unique index is stopped by the groups that repeat, counted before anything is
  created and excluding groups holding a null, because PostgreSQL's default is
  `NULLS DISTINCT`.
- Dropping issues no `CASCADE`, and the indexes behind a primary key or unique
  constraint are refused by name from the model rather than relayed as a code.

Known deviations:

- **The request waits for the build.** `CREATE INDEX CONCURRENTLY` cannot run in
  a transaction block and can leave an invalid index behind. The model reports
  `valid`, so an invalid index is at least visible.
- **A unique index is not a unique constraint.** They are different objects.
  In MySQL they are one object, dropped through the constraint (D235).
- **No reindex or rebuild**, and no storage parameters or tablespace.

Spec: [Creating and dropping an index](../../decisions/2026-08-30-index-create-drop-design.md)

## D40. A relation publishes what may point at it

What a foreign key may point at is published rather than inferred, so a target
with no matching key is named instead of being handed SQLSTATE 42830.

- Two constraint kinds are reachable: unique and foreign key. A check constraint
  is not, and will not be — its body is an expression, which is what
  [D2c](contract.md) refuses.
- Creating and dropping are one capability, for the reason D39 gives, and the
  gate is its own third one: a materialized view is indexable and holds no
  constraints, a child partition holds its own even though its columns belong to
  its parent.
- `RelationModel.candidate_keys` lists the column sets carrying a unique key — a
  primary key, a unique constraint or a bare unique index, never a partial one —
  each named by whatever provides it. The target itself is a catalog node id
  handed back as it was given ([D21](contract.md)), and the screen finds the
  candidates through two ordinary catalog calls rather than by composing an id.
- The name is the source's, as in D39, and the answer reads back which
  constraint appeared.
- Behaviour on update and delete is the closed `RefAction` set the relation model
  already reports. `validated` travels with every foreign key and check, because
  a constraint added `NOT VALID` promises nothing about the rows already there.
- A unique constraint is stopped by values that repeat, a foreign key by rows
  whose key names nothing, counted under MATCH SIMPLE so a null key is not
  counted. `RepeatingValues` and `UnmatchedRows` stay separate, because they lead
  to different work. A count can itself be refused when the two column lists
  cannot be compared, so the SQLSTATE mapping travels with the count as well as
  with the change.
- Dropping issues no `CASCADE`, and a primary key is refused outright: without one
  a relation's rows cannot be edited at all, since the versioned handle of
  [D25](relations.md) is built from the key.

Known deviations:

- **No `NOT VALID` and no `VALIDATE CONSTRAINT`.** A two-step constraint is a
  second state and a second command; the count already says what a validation
  scan would find.
- **No deferrability, `MATCH FULL` or `NULLS NOT DISTINCT`**, and no check or
  exclusion constraints.
- **The request waits for the scan**, as it waits for an index build in D39.
- **No cross-connector references.** The target is a node of the same source.

Spec: [Promising uniqueness, and pointing at another relation](../../decisions/2026-08-30-constraint-create-drop-design.md)

## D32. A rename returns its replacement identity

A relation id contains its name, so a rename changes identity as well as a
label, and open work has to be able to follow it.

- Rename goes through the same action registry the file source uses, not a
  source-specific route or a client branch. It is offered for non-system tables,
  partitioned tables, views and materialized views.
- The parameter schema accepts one exact new name, rejects surrounding
  whitespace and names over 63 bytes; the adapter checks the fresh schema for an
  existing relation before composing identifiers with `psycopg.sql.Identifier`.
- The source chooses `ALTER TABLE`, `ALTER VIEW` or `ALTER MATERIALIZED VIEW`
  from the catalog node it produced; no kind or SQL fragment comes from the
  client.
- `ActionResult.replacement` carries `old_node_id`, `new_node_id` and the new
  title. The catalog reloads the source-named parent, while the workspace
  replaces rows and structure panel identities in its layout tree without moving
  their tabs. The client copies the opaque ids and never constructs the new one.
- The replacement shape belongs to the common action boundary, so a future file
  rename or object-store move preserves open work by returning the same fact.

Known deviations:

- **Only open rows and structure panels follow the replacement.** Saved grid
  state remains under the old node id, so filters and column layout begin fresh.
  Migrating that state needs an explicit ownership and expiry rule rather than
  copying local-storage keys opportunistically.
- **External dependants follow PostgreSQL's own rename semantics.** Objects tied
  to the relation identity keep working; text outside PostgreSQL's dependency
  graph is not searched or rewritten.

Spec: [Renaming a table and a view](../../decisions/2026-08-29-relation-rename-design.md)

## D117. A designed table is planned, reviewed, then created

A whole table cannot be asked for with a form of fields, and everything about
it — types with parameters, ordered keys, index predicates, generated columns —
is exactly what [D2c](contract.md) refuses to accept as typed SQL. So the
definition is a closed model, the source composes it, and the person approves
the composition before anything runs.

- `create_table` is an ordinary catalog action on a schema, `acts_on="children"`,
  requiring `structure`. Creation goes through it, so access, refusals, cache
  invalidation and which branch to reload stay where every other change keeps
  them (D9). The editor is chosen by the `table-designer` workflow the action's
  parameter schema declares, never by the name of the action (D73).
- Two capability questions sit beside it, `table_design_options` and
  `plan_table`. A source without them answers 501. Neither creates anything.
- Where the table goes is a choice, not the accident of which schema the menu
  was opened in. The editor is handed the level's own groupings with the
  source's machinery left out — the same list a field naming a grouping is
  turned into (D56) — and moving the destination asks the server to plan again,
  because the schema is part of every statement it composes.
- The vocabulary is the server's: types and their typed parameters, index
  methods and their limits, functions with the contexts each may appear in,
  operator classes and collations read from `pg_catalog`, and whether this
  version can treat nulls as equal in a unique constraint.
- **What a source has none of is not drawn.** Beside the vocabulary the source
  declares its abilities — unique and foreign keys, deferrable ones, a key's
  order and nulls, an index's carried columns and predicate, comments,
  tablespaces — false unless declared, and the editor leaves out every field
  and section it lacks, as it leaves out the hypertable outside PostgreSQL. An
  empty or single-valued list (collations, persistence, partitioning, match) is
  left out the same way. The composer still refuses each of them: a hidden
  field is a courtesy, never the rule.
- Expressions are a closed model — literals, draft column references,
  comparisons, boolean groups, null tests, bounded membership, arithmetic,
  casts and published function codes. A function's contexts are published
  because the server has the rule: `now()` fills a column and cannot index one.
  A raw fragment, a statement separator, a subquery or an arbitrary function
  name has nowhere to enter.
- Every object carries a browser-issued draft id. Keys, indexes and expressions
  refer to columns by that id, so renaming or reordering a column changes
  nothing else, and a problem names the object the editor should select.
- One composer serves the preview and the creation. The plan carries the
  statements, warnings, per-object problems and a fingerprint over the composed
  statements; creating re-composes from the definition and refuses a fingerprint
  that no longer matches. Statements never travel in a request.
- Problems appear inside the SQL pane, so their arrival does not resize the
  editor. When an invalid draft has no statements, the pane keeps the last
  valid SQL marked as previous; it is never offered for review or creation.
- Planning executes nothing. That is deliberately not D46's rehearsal: DDL that
  runs and is rolled back still takes locks and still fires whatever the server
  hangs off it, which is not a thing to do while somebody is typing.
- The whole creation is one transaction, so an index the server refuses leaves
  no table behind. A taken name is a conflict, never an implicit replacement; a
  name the source derives is nudged past what the schema already holds, and a
  name somebody typed is refused instead.
- The server states the rules a form would otherwise guess: a primary-key column
  must require a value, a partitioned table's keys must hold its partition
  columns, `SET NULL` cannot meet a required column, a foreign key needs a
  candidate key its target publishes, and the two sides must be comparable —
  asked of `pg_operator` through implicit casts, because `=` for `varchar` is
  `text`'s operator.

Known deviations:

- **A MySQL plan is one statement**, with every key and index inside it,
  because MySQL commits each structure statement by itself (D236).
- **A ClickHouse plan is one `CREATE TABLE … ENGINE = MergeTree`**, its primary
  key the sorting key and said to be no promise of uniqueness; unique keys,
  foreign keys and identities are not drawn, and refused if sent (D274).

- **Exclusion constraints are not implemented.** They need operator metadata per
  method and type beyond the operator classes published here, and the design
  names them as part of the intended feature.
- **Temporary tables are deliberately absent.** Their lifetime is a database
  session and a pooled request cannot promise one.
- **A draft lives in the window that holds it.** Nothing is persisted across a
  reload, and a second session sees nothing of it.
- **Nothing offers to open the new table.** The action returns its source-issued
  id and the catalog branch reloads, so it is there to click; the offer itself
  is not built.

Spec: [Creating a table with an object editor](../../decisions/2026-09-06-table-designer-design.md)
