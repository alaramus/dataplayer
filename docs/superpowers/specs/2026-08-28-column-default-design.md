# Column default

## Decision

The form can set a literal value or drop the default. The request is a closed
action, `set | drop`: `set` requires a string value, `drop` carries none. The
empty string stays a full literal.

User text never becomes an SQL fragment. PostgreSQL is given a quoted literal
and coerces it to the column's own type. Quotes are therefore safe, and an
invalid number, date or UUID is rejected by the source. A generated column
takes no default.

## Interface

The command sits on the column's row in Structure. The dialog shows the current
default, accepts a new literal value, and separately offers to drop the
existing one. Structure and data are re-read after a success.

## Deferred

SQL expressions (`now()`, sequences, functions), and changing a column's
nullability or type. Expressions will need a source-owned vocabulary rather
than a field holding arbitrary SQL.
