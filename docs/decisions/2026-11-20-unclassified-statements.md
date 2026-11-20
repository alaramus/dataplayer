# Statements the console cannot classify

Date: 2026-11-20. Decision: D383. Amends D62 and D66.

Every dialect module classes a statement, and `unknown` was refused in every
mode. That made the reach of the console the reach of a parser. In
PostgreSQL it was not even the parser: pglast reads `DO $$…$$` and `CALL p()`
exactly, and they were `unknown` only because no class was written for their
nodes. In MySQL and ClickHouse it was sqlglot: `KILL QUERY`, `CALL`, `FLUSH`,
`UNDROP` and whatever DDL form came out after the installed version fall back
to a bare command. A person who may change the database could not do there
what the database would let them do.

D62 already says what the boundary is: the transaction and the database role
enforce; classification supplies policy and explanation, not proof. So a
statement the console cannot classify is not refused for that reason. It runs
through the strictest gate the console has.

## What `unknown` means

Before this decision `unknown` meant three things at once:

1. the parser could not read the text;
2. it read it, and nothing says what the statement does — `DO`, `CALL`,
   `KILL`, a command sqlglot keeps as a keyword and the rest;
3. it read it, and the application wanted it refused — renaming a schema,
   moving a relation into another schema, `GRANT role TO user`, MySQL's
   `DROP USER`.

The third is not "unknown"; it was a refusal spelled as one. Every such form
now carries its refusal in words (`refused`), and only the first two stay
`unknown`: the effect of the statement cannot be read out of its text.

## Families refused whatever the parser says

D66's vocabulary is closed: roles and permissions, plugins and extensions,
the server itself, replication, backups, and the transaction and session the
console owns are not administered from a text box. A form of one of those
families that the parser does not model would now run instead of being
refused, so each dialect module refuses them by their leading words when the
parse gave no class: `DROP USER`, `INSTALL PLUGIN`, `SHUTDOWN`, `CHANGE
REPLICATION SOURCE`, `XA`, `LOCK TABLES` in MySQL; `MOVE USER`, `SET ROLE`,
`BACKUP`, `RESTORE` in ClickHouse. PostgreSQL parses everything and names the
nodes instead.

D62 rejects the first word as a substitute for classification. That is about
granting: a first word that admits a statement would admit `SELECT` followed by
anything. Here the words only take away; a statement they match is refused,
and one they do not match still meets the strictest gate. That direction is
safe to read off tokens, and it is stated beside the lists.

## The gate

A statement of class `unknown`, on a source that declares it may run one:

- is a change. It is in the server's set of changing classes, so it needs a
  run that is not a read, the owner's policy not `read_only`, and the
  confirmation `confirm_writes` asks for;
- needs `own` access. Nothing in it says how far it reaches, so it needs the
  most a grant gives;
- is high risk, asked about every time, with the question saying that
  DataPlayer cannot tell what the statement does and the database decides;
- runs alone, with no transaction, the way maintenance does (D206). Nothing
  says it tolerates a transaction — `CALL` of a procedure that commits does
  not, and MySQL commits some statements by itself — and with nothing to roll
  back, it shares a run with nothing. It is refused in a manual transaction,
  which the UI owns (D66), and it is not rehearsed;
- runs on a connection that is closed afterwards rather than returned to the
  pool. A `DO` block can `SET ROLE`, a procedure can change a session
  variable; resetting what is known to be set is not enough when what was
  set is not known;
- invalidates the whole connection after it succeeds, as any statement whose
  effect the module cannot take apart already does (D66).

A read run still refuses it: MySQL's read-only transaction does not stop a
statement that commits by itself, and `KILL` is not stopped by any.

## Which sources

A source says whether it runs unclassified statements in its query profile
(`runs_unclassified`). It is true only where an authority other than this
classifier stands behind the run: a server and its role. PostgreSQL, MySQL and
ClickHouse say true. SQLite runs inside this process behind its authorizer,
Cassandra's module classes by first words, and the file source runs DuckDB in
the backend; all three keep refusing `unknown` until somebody shows their
boundary holds without the classifier.

An owner-level switch, "run statements the console cannot classify", was
considered and rejected: `own` access and a confirmation every time already
are the owner's say, and a second switch would be a second place to look for
why something did not run.

The agent does not run unclassified statements. A person confirming "run one
statement that changes data" did not read the statement the agent wrote, and
the gate above depends on somebody who did.
