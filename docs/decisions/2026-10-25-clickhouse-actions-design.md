# ClickHouse catalog actions

Decision D276. The second half of the fifth slice of the ClickHouse source:
the actions a catalog offers on a database, a table or a view.

## The same actions as MySQL's

New database, Drop database, Rename, Move to database, Drop, Load from CSV,
Create table and Model as code, with the shapes MySQL's have (D238), so the
screens need nothing new. A database is not renamed from the catalog, as on
MySQL; ClickHouse's `RENAME DATABASE` stays a statement for the console, where
whoever runs it can see what refers to the database by name.

## Previews without rehearsal

PostgreSQL rehearses a drop in a transaction it rolls back (D66); MySQL cannot,
and reads `information_schema` for the foreign keys in the way (D238).
ClickHouse cannot either, and has no foreign keys to stop a drop. What a drop
breaks is a materialized view fed by the table: it keeps reading from a table
that is gone, and fails on every insert into its source. `system.tables`
records each such view as a dependency of its source table, and the preview
names them. A plain view is not recorded anywhere and is not named; the guide
says so.

A set is dropped views first, so a materialized view in the set goes before
the table it reads and the server does not refuse the table for it.

## Move

`RENAME TABLE a.t TO b.t` moves a table or a view between Atomic databases,
which is ClickHouse's default engine for a database, so Move applies to views
as well as tables, unlike MySQL's.

## A dropped table too large

ClickHouse refuses to drop a table larger than `max_table_size_to_drop`, 50 GB
by default. The refusal is passed on as a sentence naming the limit and who
can raise it, rather than worked around: the limit is the server
administrator's guard, not this application's to lift.
