# ClickHouse reports, search and export

Decision D275. The first half of the fifth slice of the ClickHouse source: a
System section of reports, stopping a query or a mutation from it, search, and
exporting every matching row. Catalog actions follow in their own commit.

## Which reports

ClickHouse already lists all of itself as tables of the `system` database,
which the catalog shows like any other. The reports are therefore a selection
for a person, each a statement written here: what is running (processes),
what is rewriting tables (mutations, merges), what takes space (table sizes,
disks), what was configured (changed server settings), what is counted now
(metrics) and who may sign in (users). Columns are renamed to plain words and
sizes kept as numbers so that they sort.

The settings report reads `system.server_settings` rather than
`system.settings`. The session's own list would be filled by the settings every
request of this adapter carries (D268) and say more about DataPlayer than
about the server.

## Stopping what a report shows

A query is stopped by its id with `KILL QUERY … SYNC`, which answers a line
for each query it stopped, so the count reported is the server's.

A mutation is the other thing worth stopping: one that fails holds up every
later change of its table (D273), and stopping it is the server's documented
way out. `system.mutations` names a mutation by `mutation_id`, which repeats
from table to table (`mutation_3.txt`), and a row command is identified by one
column. The report therefore gives each mutation an id that is a hash of its
database, table and mutation id, and `KILL MUTATION` finds it by the same
hash. The id is a number, checked as one before it is bound.

## Search

MySQL's search ranks inside one SQL statement (D237); SQLite reads its catalog
whole and ranks in Python (D257). A ClickHouse catalog can be large, and its
SQL has no simple equivalent of the word rule's "every word at the start of a
word of the name". The server therefore narrows — a name, a column's name or
a comment holding every word, by `positionCaseInsensitiveUTF8` on bound
values — and this package classes what it gets by the shared rule. The
candidates are bounded at five thousand, and a search that reaches the bound
says the answer may be incomplete.

Every output column of a search statement is renamed to a word no source
column uses. ClickHouse's aliases belong to the whole query, not to one
`SELECT`: `'' AS name` beside `name AS database` replaced the column `name`
itself and returned every database as the empty string, which a test caught.

## Export

Every matching row is read from one request whose answer is not buffered by
the server, a batch at a time; a reader that stops closes the request, which
stops the read on the server (D271).
