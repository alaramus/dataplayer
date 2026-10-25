# Changing ClickHouse structure

Decision D273. The first half of the fourth slice of the ClickHouse source:
columns and skipping indexes changed from the structure screen. The table
designer and a table made from rows follow in their own commit.

## A failed conversion breaks the table

MySQL tries a type change and counts what stood in the way once it has been
refused (D235): a refused `MODIFY` changes nothing there. ClickHouse is the
other way round. `ALTER TABLE … MODIFY COLUMN` changes the column's type in
the table's metadata at once and converts the existing parts in a mutation
afterwards. A mutation that meets a value it cannot convert — `abc` into an
`Int32`, a NULL into a column that now requires a value — fails, and is left
in place: every read of the table then tries the conversion and fails with it,
and every later `ALTER` waits behind it. This was seen on the test server, not
read about.

So the order is reversed:

- what would stop the conversion is counted first — values for which
  `accurateCastOrNull` to the new type is NULL, or NULLs before a column is
  made to require a value — and while the count is above zero the change is an
  answer with that number and nothing is altered;
- if the mutation fails all the same, it is killed with `KILL MUTATION … SYNC`
  and the column given its old type back, which is a change of metadata only,
  since the parts were never converted. A test drives this path with a value
  the count did not see.

`accurateCastOrNull` is stricter than the `CAST` the mutation uses: it refuses
`1.5` into an integer where `CAST` would truncate. Refusing a change that would
lose data is the side to err on, and it is recorded as a deviation.

The vocabulary of types is scalars only, so every target is one
`accurateCastOrNull` can try.

## What stays where it is

A column of the sorting, primary or partition key cannot be dropped, renamed
or changed in type: the server refuses it, since the key decides which part
and which place in it a row is kept in. The adapter says so before asking,
with the column's name, rather than passing on the server's sentence about
"key expressions".

`MODIFY COLUMN c NewType` with nothing else keeps the column's default, its
comment and its codec, so unlike MySQL there is no definition to read back and
edit in one place.

A default is a query parameter typed as the column: the server parses it as
that type, refuses one the type cannot hold, and stores it as a constant. The
literal never passes through this application's own quoting.

## Indexes

ClickHouse's indexes are data skipping indexes: they let a read skip granules
that cannot hold a value, and never refuse a row. Three of the kinds are
offered — min and max, a set of up to a hundred values, a Bloom filter — and
none is unique. An index added with `ADD INDEX` covers only parts written
afterwards; `MATERIALIZE INDEX` builds it over the parts already there, and an
index whose building fails is dropped again rather than left half made.

The primary key appears among the indexes (D269) and is not dropped: it is
part of the table's definition, changed only by making the table again.

ClickHouse has no unique key and no foreign key, so the constraint capability
is not claimed at all, and the relation model says why.
