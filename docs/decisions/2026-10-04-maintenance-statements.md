# Maintenance commands in the SQL editor

Date: 2026-10-04. Decision: D206. Amends D62 and D66.

`analyze;` was refused in the editor. The dialect module classified it as
`unknown`, and D62 refuses what it cannot classify. That rule is right for a
form nobody has taught it; ANALYZE, VACUUM, REINDEX, CLUSTER, CHECKPOINT and
REFRESH MATERIALIZED VIEW are not such forms. They are the routine care of a
PostgreSQL database, and a person who manages one expects to run them where
they run everything else.

They are one class, `maintenance`, decided by the leading keyword like the
other families the parser has no grammar for. The class changes the source —
not its rows, but its statistics, its storage and its indexes — so it is
treated as a change: write access, the owner's confirmation policy, and never
a read-only run. Structure access was considered and rejected: maintenance
alters no definition, and a person allowed to write rows may reasonably keep
the table they write in healthy.

PostgreSQL refuses VACUUM, CLUSTER without a table and any CONCURRENTLY form
inside a transaction block, and every run of the editor is a transaction. Two
ways were weighed: run only what tolerates a transaction (ANALYZE, CHECKPOINT,
REINDEX of one table) and refuse the rest, or run maintenance with no
transaction. The first leaves VACUUM — the command people actually reach for —
unusable, so maintenance runs with no transaction: the source switches the
borrowed connection to autocommit, sets the timeout and schema context for the
session rather than the transaction, and resets both before the connection
returns to the pool, closing it if it cannot be reset.

With no transaction there is nothing to roll back. A maintenance command
therefore runs alone: not beside other statements in a script, where a failure
after it would report a rollback of something the server had already kept,
and not inside a manual transaction, which it would refuse anyway. Both are
refused before a run exists, with a sentence saying why. Rehearsal, which is a
rolled-back transaction, is refused for the same reason.

What blocks readers is asked about every time, as a high-risk statement under
D66: VACUUM FULL and CLUSTER rewrite the table; REINDEX and REFRESH
MATERIALIZED VIEW lock it unless told CONCURRENTLY. A plain VACUUM, ANALYZE and
CHECKPOINT ask only what the connection's policy asks.

Which classes change a source was a pair of literals in six places on the
server and one in the editor. It is now one set on the server, and each
prepared statement carries `changes`, so the editor no longer keeps a second
list that a new class would silently fall outside.
