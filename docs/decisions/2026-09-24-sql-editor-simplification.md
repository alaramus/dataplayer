# SQL editor permissions and immediate deletion

Date: 2026-09-24. Decision: D160. Revises D63 and D66.

The connection already has an owner-controlled execution policy and an access
grant. A second read/write unlock in each SQL editor duplicates that choice.
The editor runs a read in a read-only transaction and a change in auto-commit,
based on the source's preparation of the exact text being run. A person can
choose a manual transaction to hold changes until Commit or Rollback. That is
transaction control, not another permission. The server still checks the
connection's current policy and grant before a write. Under `confirm_writes`,
the person confirms each changing run. High-risk statements still require the
specific confirmation and DDL rehearsal described by D66.

The saved-query library has Queries and History. A saved query is deleted
permanently after confirmation; there is no Trash, restore or delayed sweep.
The migration permanently removes documents already in Trash and the unused
write-unlock records. Run history remains on its own retention policy, and a
run survives deletion of its source document with a null document reference.
