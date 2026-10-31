# MongoDB queries in the query console

Decision D296. Revisits part of D286: `mongosh` in a terminal stays, and the
query console every SQL source has now runs MongoDB as well, with its results
in the grid.

## Why it was revisited

D286 put three answers to the user and took the terminal. A query then had no
grid, no history, no download, no chart and no pinned result: the terminal
prints text, and anything to be looked at again had to be run again. The user
asked for the console the other sources have.

The terminal is not replaced. It keeps everything the console does not read:
variables, functions, loops, helpers, completion of the whole shell.

## What the console reads

The first of D286's three answers: a part of the shell's own syntax, parsed by
the server into driver calls. JavaScript is never run. The alternatives were:

- runCommand documents only — the same driver calls in a form nobody writes;
- the shell's own output scraped from a container — rejected: it is text made
  for a terminal, and a result would be parsed back out of it.

What is read, chosen by what people type into `mongosh` for a query:

- `db.<collection>`, `db["…"]`, `db.getCollection("…")` and
  `db.getSiblingDB("…")` before either;
- reads: `find` with `sort`, `limit`, `skip`, `projection`, `hint`,
  `collation`, `comment`, `maxTimeMS`, `batchSize`, `allowDiskUse`; `findOne`,
  `aggregate`, `countDocuments`, `estimatedDocumentCount`, `distinct`,
  `getIndexes`, `getCollectionNames`, `getCollectionInfos`, `stats`,
  `show dbs`, `show collections`;
- `explain()` after `find` and `aggregate`, and `explain()` before them;
- writes: `insertOne`, `insertMany`, `updateOne`, `updateMany`, `replaceOne`,
  `deleteOne`, `deleteMany`, `findOneAndUpdate`, `findOneAndReplace`,
  `findOneAndDelete`;
- structure: `createIndex`, `createIndexes`, `dropIndex`, `dropIndexes`,
  `drop`, `renameCollection`, `createCollection`, `createView`,
  `dropDatabase`;
- `db.runCommand({…})` and `db.adminCommand({…})`;
- `use <database>` for the statements after it in the same run.

Values are spelt the shell's way: unquoted keys, single quotes, trailing
commas, comments, regular expression literals, `NaN`, `Infinity`,
`undefined` (as null) and the constructors `ObjectId`, `ISODate`, `new Date`,
`NumberLong`, `NumberInt`, `NumberDecimal`, `UUID`, `BinData`, `Timestamp`,
`MinKey`, `MaxKey`, `RegExp`. An integer literal is an int or a long by size,
not the shell's double: a large identifier keeps its digits.

The old shell's `count`, `insert`, `update`, `remove` and `save` are refused
with the method to use instead. Anything else is refused with a sentence that
names the method and says the terminal runs the rest.

A statement ends where its chain of calls ends: at a semicolon, or where the
next token cannot continue it. One statement a line needs no semicolon, and a
`.sort()` on the next line still belongs to the `find` above it. A statement
that does not parse is refused up to the next line that starts one, so a
mistake does not hide the statements after it.

## Classes, risk and confirmation

The class comes from the method called, because the server has no read-only
session to enforce a read: `find` reads, `insertOne` is `dml`, `createIndex`
is `ddl`. A pipeline ending in `$out` or `$merge` is `dml`; `$out` replaces
its target, so it is destructive. `explain` reads, because an explained write
does not write.

A command is classed by its name: a closed list of reads, the four write
commands, `compact`, `validate` and `reIndex` as maintenance, and the rest as
`ddl`, asked about every time and invalidating the whole connection. Users and
roles, shutdown, replica set, parameter, session and transaction commands are
refused: they are administration, which the console does not do for SQL
either.

High risk: every drop, `updateMany` and `deleteMany` with an empty filter,
`$out`, a rename that drops its target, every command that is not a read.

## Results

A cursor's documents are rows, with columns found the way a collection page
finds them (D284): every top-level field met, `_id` first, cells as text,
nested values as relaxed Extended JSON. A count and `distinct` are one column.

A command's answer, a plan and a write's acknowledgement (`insertedId`,
`matchedCount`, …) are one document, drawn as a tree with the viewer D295 made
for the catalog. The user picked the tree because it is the viewer that
exists; a one-row table would put every field in a cell of its own and lose
the nesting. The tree belongs to the captured result rather than to the run
record, which keeps no rows (D64).

## Execution

Every statement is one driver call. MongoDB holds no transaction here — a
standalone server has none, and a change is kept the moment it ends — so, as
on ClickHouse (D271), a run that changes anything holds that statement alone,
with any `use` before it, and there is no manual mode.

The time limit is pymongo's own (`pymongo.timeout`), which the server is told
as `maxTimeMS`; a shorter `maxTimeMS` in the text wins. Stop cancels the call
and kills the server's operation by the comment the call carried, best effort:
a user who may not list operations is still stopped by the limit.

The database is the first of the console's context, else the connection's.
A connection that names none refuses a statement that needs one and says to
write `use` or `getSiblingDB`.

## What else changes

- The query profile says which language the editor highlights, `sql` or
  `javascript`, and `none` joins the parameter syntaxes: the shell has no
  placeholders, a value is written into the call.
- Completion lists the databases and the context database's collections and
  says its knowledge is incomplete, so nothing is marked as missing.
- The grid's Query command opens `db.<collection>.find({}).limit(100)`.
- The agent's query tool says that MongoDB takes the shell's syntax.

## Rejected

- **Variables between statements.** A run would need a scope the server keeps,
  and the line between this and running JavaScript would move with every
  request.
- **A Mongo-specific Explain command.** The console's Explain is a plan tree
  with costs (D65); MongoDB's plan has no such numbers, and `explain()` in the
  text already answers as a document.
