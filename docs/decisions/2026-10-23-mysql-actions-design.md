# MySQL catalog actions

Decision D238. The second half of the fifth slice of the MySQL source: what
the catalog's action menu offers on a MySQL connection.

## What is offered

PostgreSQL's catalog actions, where MySQL has the thing they act on:

- **New database** at the top of the connection.
- **Drop database** on a database.
- **Rename** a table or a view.
- **Move to database** for a table.
- **Drop** for one relation or a selection.
- **Load from CSV** into a database.
- **Create table**, the designer of D236.
- **Model as code** for a database, a table or a view.

The server's own databases — `mysql`, `information_schema`,
`performance_schema`, `sys` — offer only the model, as PostgreSQL's system
schemas offer nothing that changes them.

Not offered:

- **Renaming a database.** MySQL has no statement for it. The way around it is
  creating a new database and moving every table into it, and that leaves the
  views, routines, triggers and events behind, because none of them can be
  moved between databases. A rename that loses half of what was there is not a
  rename, so the action is absent and the guide says why.
- **Roles.** PostgreSQL offers New role on its Roles report. MySQL accounts
  have a host as part of their name and a password policy of their own. That
  is a form of its own, left for later.

## Nothing can be rehearsed

PostgreSQL's drop preview runs the drop and rolls it back, so what it lists is
the server's own account of the cascade. MySQL commits every structure
statement by itself (D233): a rehearsal would be the drop. A MySQL preview
therefore reads `information_schema` for what the change would meet, and the
change checks the same thing again before it runs.

## Foreign keys that point in

MySQL has no CASCADE on a drop: a table another table refers to is refused.
The two servers refuse differently:

- MySQL 8 has atomic DDL. `DROP TABLE a, b, c` drops all three or none, and
  the tables may be named in any order.
- MariaDB drops the tables named before the one it refuses, and refuses a
  parent named before its child even when both are in the statement.

These were checked against both servers before choosing:

1. A drop reads `REFERENTIAL_CONSTRAINTS` for keys of tables outside what is
   being dropped that point into it. Each one is named in the preview, which
   is blocked, and the drop is refused with the first of them. That is the
   only case where the server would refuse, and on MariaDB it is caught before
   anything is gone.
2. What remains are keys between the tables being dropped. The drop runs with
   `foreign_key_checks` off for its own statements on its own connection, and
   restores the session's value afterwards. So a parent and its child go
   together in any order on both servers.

Dropping a database follows the same rule: a key from another database into
it blocks it. The keys inside it are the server's to drop with it.

## What a preview counts

- A database: its tables, views, routines, triggers and events, as counts.
  A database that holds anything needs **Also drop everything in it** ticked,
  as a non-empty PostgreSQL schema needs its cascade.
- Relations: the triggers that go with the tables, by name. On MySQL, the
  views outside the selection that read a dropped table, from
  `VIEW_TABLE_USAGE`, since such a view stays and fails when it is next read.
  MariaDB keeps no such list, and a guess from the text of its views would
  name the wrong ones, so there it names none.

## Moving and renaming

Both are `RENAME TABLE`, which carries the foreign keys that point at a table
along with it. A view can be renamed but cannot change database (MySQL's
1450). A table with triggers cannot change database either (1435). Both are
refused before the statement is sent, in words, and the codes stay as a
second line of refusal.

## A loaded file

Loading a CSV file is the second implementation of the same action, so what
both share moved to `adapters/csv_load.py`: the form, the two ceilings, the
file's name as the table's, and the choice and renaming of columns. Each
source keeps its own rule for names and its own way of making the table.
MySQL's columns are all TEXT rather than the designer's default VARCHAR(255),
which would refuse the first cell longer than that, and the table is made as
a table from rows is (D236): checked first, and dropped again if its rows are
still refused.
