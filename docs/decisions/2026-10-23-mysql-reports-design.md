# MySQL reports, search and export

Decision D237. The first half of the fifth slice of the MySQL source: what the
server says about itself, stopping another connection's work, search over the
catalog, and downloading every matching row. The catalog's own actions —
databases and relations created, renamed and dropped — are the second half.

## Where the reports live

PostgreSQL's reports sit in a section of the catalog after its schemas, and
MySQL's follow the same shape: a **System** node after the databases, with
one report under it per question. Its id is `\system`. A database id writes
every backslash in a name as two, so no database, however it is named, has an
id beginning with a single backslash followed by a letter. A prefix that
could also be a database's name — `system`, `.system` — would have needed a
rule about which wins.

The reports are:

- **Processes**: the connections open now, what each is running and for how
  long.
- **Variables**: every global setting.
- **Status**: the counters the server keeps since it started.
- **Users**: accounts and the hosts they may connect from.
- **Routines** and **Triggers** outside the server's own databases.
- **Events**: what the scheduler runs.
- **Engines**: the storage engines and which is the default.

Each is a statement written in the package and chosen by node id. Nothing in a
request reaches it except the filters, sorting and page, which are applied
over it as over a relation (D231).

## One type, two servers, and an answer that moved

A single source type covers MySQL and MariaDB (D228), and the reports are
where they differ most:

- Variables and status are in `performance_schema` on MySQL, and in
  `information_schema` on MariaDB, which names them in capitals.
- MariaDB's `mysql.user` is a view with no `account_locked`, and lists roles
  beside accounts, so its Users report says which rows are roles instead.
- MySQL deprecated `information_schema.PROCESSLIST` and warns on every read
  of it. Its replacement, `performance_schema.processlist`, arrived in 8.0.22,
  after the supported floor of 8.0.16. `performance_schema.threads` is older,
  but it is refused to a user without SELECT on it, while both lists show such
  a user its own connections.

So a report carries a statement per flavour where the answer differs, and the
processes carry one more for MySQL before 8.0.22. Every statement was run on
both servers in the suite rather than assumed from the documentation.

## Columns as the server describes them

A report's columns are not declared next to its statement. The server is
asked for them with the statement wrapped in `SELECT * FROM (…) AS report
LIMIT 0`, and each wire type is read the way a console result's is. A
declared list would be a second copy of the statement's select list, and it
would drift from it the first time a column is added on one server and not the
other.

The page is the same subquery with a WHERE, an ORDER BY and a LIMIT. A report
names the columns that make its order stable — a process by its id, a
variable by its name — and they follow whatever the reader sorts by, as a
table's key does, so that page two does not repeat page one.

## What a report is not

A report is a moment of the server. Nothing is written through it, a row of
one is not a record (D111), and the page offers no command to make a table of
it (D72): a copy of a moment cannot be refreshed. Processes are read again
every five seconds, status every ten; the rest are read when opened.

## Stopping a connection

Processes offer **Cancel query**, which is `KILL QUERY` and leaves the
connection open, and **Terminate**, which is `KILL CONNECTION`, as row
commands (D70). They need the structure level, like PostgreSQL's: stopping
somebody else's work is not what may-write-rows means.

Each key is checked to be a whole number before anything is sent, and is bound
as a parameter. The server's refusal of one connection does not stop the
rest; it is reported by error number: 1094, the connection has already
ended, and 1095, this user may not stop it. Any other error is the source
failing.

## Search

Search by name and by column (D202) is one query of `information_schema` per
search, as PostgreSQL's is one of `pg_class`.

- Every word is found with `INSTR` against a bound value. `%` and `_` are
  characters, and nothing typed is compiled.
- Names are compared after `LOWER` under `utf8mb4_bin`. The server's default
  collations ignore accents and trailing spaces, so they would find names the
  word rule does not hold. The catalog's columns are also in another
  character set, which INSTR refuses as a mix of collations.
- Each word is bound twice, as the rule folds it and as typed for the server to
  fold, because Python and MySQL fold `ß` differently.
- Exact, prefix, word and substring are ranked inside the query, before its
  LIMIT, so the best names are never the ones a full page cuts.
- The suite holds the query to the shared word table, as it holds every other
  implementation.

A column search keeps the best match per relation: a column's name by its
class, then a column's comment, then the table's own. A view's comment is
skipped, because MySQL writes the word VIEW there itself. The reports are
found by their titles in the reader's language, without asking the server.

A search past its clock is cancelled on this side. The read closes its
connection rather than handing a half-read answer back to the pool.

## Export

Downloading every matching row (D45) prepares the same read as a page, so the
same filters and sorting are checked the same way, and streams it with an
unbuffered cursor in bounded batches. A connection left in the middle of an
unbuffered result cannot be used again, so one whose reader stopped early is
closed rather than returned to the pool.
