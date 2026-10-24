# Designing MySQL tables

Decision D236. The second half of the fourth slice of the MySQL source: the
table designer, and a table made from rows. It also brings the source's first
catalog action, creating a designed table; the rest of the actions follow in
the next slice.

## One statement

PostgreSQL's plan for a designed table is a `CREATE TABLE`, then one
`CREATE INDEX` per index and one `COMMENT ON` per comment, run in one
transaction. MySQL commits every structure statement by itself (D233), so the
same plan run on MySQL could stop after its second statement: the table would
exist without the index that was reviewed with it, and nothing could undo it.

MySQL takes indexes inside `CREATE TABLE`, and comments as column and table
options, so the whole design fits in one statement. The server either makes
all of it or none of it. The alternative was running several statements and
dropping the table when a later one failed. That would leave a window in which
the half-made table can be seen and written to.

## What MySQL lacks is named before the review

The designer is shared with PostgreSQL, and it offers choices MySQL does not
have. Two ways to handle that were considered:

- **Compose the statement anyway and let the server refuse it.** The refusal
  would come after the person has reviewed and accepted the plan, as a code
  with no object attached.
- **Make each one a plan problem on the object that asks for it.** The editor
  already selects an object when the plan names it.

The second is chosen. The plan names these:

- a deferrable constraint;
- MATCH FULL;
- SET DEFAULT, which InnoDB accepts and does not carry out;
- NULLS FIRST or LAST;
- an operator class;
- INCLUDE;
- a partial index;
- UNLOGGED, partitioning and a hypertable;
- an array;
- nulls not distinct;
- an identity that is ALWAYS or steps by more than one;
- on MariaDB, an expression in an index.

Where the options carry a list, the list simply lacks the choice: one
persistence, one match mode, no SET DEFAULT. Deferrability and INCLUDE are
drawn by the designer whatever the options say, which is a known deviation.

An identity becomes AUTO_INCREMENT. MySQL allows one per table, and requires
it to lead a key. The plan says so instead of passing on the server's 1075.
The identity's start becomes the table option `AUTO_INCREMENT=`, and its step
is a server setting rather than a per-column property.

## Literals in a reviewed statement

The plan is text a person reads, so a literal default is written into it
rather than bound. How MySQL reads a backslash in a string depends on
NO_BACKSLASH_ESCAPES, so the plan reads the session's mode and writes the
literal for it. The statement then runs on a connection whose mode is the
same, with only STRICT_ALL_TABLES added. An expression default is written in
parentheses, which MySQL 8 requires for everything but the clock.

The functions that are not deterministic — the clock and UUID() — are offered
for a default only. MySQL refuses them in a generated column, a check or an
index, as PostgreSQL refuses `now()` in an index.

## A table made from rows

D45 makes a relation and its rows one request so that a refused row leaves no
empty table behind. PostgreSQL does it with one transaction, which MySQL
cannot give. So every value is checked against the chosen types before the
table is made, through the same temporary-table probe an insert uses (D234).
If the rows are still refused once the table exists, the table is dropped
again. That table is known to be this request's own, because `CREATE TABLE`
succeeded on a name that was free.
