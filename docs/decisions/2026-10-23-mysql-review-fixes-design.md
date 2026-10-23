# MySQL review fixes

Decisions D242 and D243, and three fixes, from a review of the MySQL source
in the browser.

## The first column's type (fix)

The table designer builds its draft before the destination's options arrive,
with PostgreSQL's `text` as a placeholder, and swaps it for the first type the
destination publishes when the list of types changes. A second designer over
the same destination found the options already in the query cache. The list
never changed after the window opened, so the placeholder stayed, and MySQL's
plan refused it: `Unknown column type "text"`. The swap now also runs when the
window opens.

## No hypertable row for a source without hypertables (fix)

The designer always listed the hypertable section. A PostgreSQL database
without TimescaleDB is offered it and says why it is unavailable: the
extension can be installed. MySQL has no such thing, so its section was a
set of disabled controls with no reason. The hypertable offer now says
whether the source has the concept at all (`offered`). The designer leaves the
section out where it has not.

## A database is called a database (fix)

A MySQL database is a `schema` node (D229), and the screens that pick a schema
said "schema" — a word a MySQL user never sees anywhere else for it. Changing
the node's kind would change what every action, the designer and the copy
apply to. So the node says what its source calls it instead
(`term: "database"`). The catalog's selector, the table designer, copying
tables, loading a file and saving rows as a table read it and say "database".

## D242. A row of a table with no key is named by its values

D234 left a table with no primary key and no non-null unique key without edits
or deletes. PostgreSQL edits such a table by `ctid`. MySQL has no row address
a client can read; InnoDB's hidden row id is not exposed.

The alternatives were:

- **Keep refusing.** Safe, but a table loaded from a CSV file has no key, and
  it is exactly the table somebody wants to correct a cell in.
- **Name the row by its values and change one with LIMIT 1.** What other tools
  do.

The second is chosen, with the checks D234 already has:

- The handle carries every value the page showed, and the digest of them.
- The row is found again under `FOR UPDATE` by every column that compares
  exactly. Text, enums and sets are compared as bytes, because a
  case-insensitive collation would find `A` for `a`. Floating-point numbers,
  JSON and shapes are left out: none of them equals the text it was shown as.
  A FLOAT holding 1.1 is not equal to 1.1.
- The digest decides among what was found. Rows the same in every value are
  interchangeable, so the change goes to any one of them, with `LIMIT 1`.
  Rows alike in the compared columns but different in the others cannot be
  told apart, and the change is refused with that reason rather than guessed.
- Identical rows get handles of their own (an occurrence number), because a
  page and a selection tell rows apart by their handles. Deleting two of three
  identical rows deletes two.
- A row whose values exceed 64 KB gets no handle: the handle travels to every
  page and back.

After a change the row is read back by its new values. If that finds rows it
cannot tell apart, the values written stand for the row, and its next change
is checked against them.

## D243. A MySQL account is made from the Users report

PostgreSQL's Roles report has New role (D79). MySQL's Users report gets
New user, with the same restraint:

- It needs `own`. An account is the server's and signs in through every other
  connection to the same server, so being able to change rows is no reason to
  be able to make one.
- It asks for a name, a host and a password. A MySQL account is a name and the
  host it may connect from, and `%`, anywhere, is the default.
- It grants nothing, or SELECT on the database the connection names when that
  is ticked. MySQL has no privilege to connect, which is what PostgreSQL's form
  grants, so reading one database is the closest useful equivalent. Global
  privileges, roles and GRANT OPTION are not offered.
- The name, the host and the password are bound. MySQL takes them as quoted
  strings, and the driver's quoting is used rather than this repository's. A
  password with a quote and a backslash is in the suite.
- An account that exists is a conflict. A grant the server refuses drops the
  account it was meant for, because an account that cannot read what it was
  made to read is not the one that was asked for.
