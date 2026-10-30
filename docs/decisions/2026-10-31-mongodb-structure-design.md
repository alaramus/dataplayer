# MongoDB structure

Decision D288. The fourth slice of the MongoDB source (D283–D287): what the
structure screen can change in a collection.

## What a column is to change

The structure screen speaks of columns because every other source has them.
A MongoDB collection's columns are found in its documents (D284), so changing
one can only mean changing those documents. Each of the screen's operations
was weighed against that:

- **add** — a field set to null in every document that lacks it, so it is a
  column from then on. A field that must have a value has none to start with,
  so a new field is always nullable;
- **drop** and **rename** — `$unset` and `$rename` over every document, which
  are exactly what a person would type in `mongosh`;
- **type** — `$convert` in a pipeline update. The server converts and may
  fail on a value, so the failures are counted first, the way PostgreSQL's
  type change counts unreadable rows (D40), and nothing is written if there
  are any;
- **default** and **nullability** — not offered. MongoDB has no default, and
  nullability would be a validator rule; a validator is a JSON Schema better
  edited where it is written, in `mongosh`.

## Indexes

MongoDB's index kinds are not methods in PostgreSQL's sense but what stands
beside each field of the key: `1`, `-1`, `"hashed"`, `"text"`, `"2dsphere"`.
They are offered as the methods the screen already knows, with their limits
stated by the source (`unique_supported`, `multi_column_supported`) rather
than worked out by the screen. A compound index with fields in different
directions is not offered: the screen's request has one method for all its
columns, and such an index is one line of `mongosh`.

A unique index over repeated values would be refused by the server with the
first duplicate it met. Counting the groups first answers in the screen's own
terms (`IndexBlocked`), as PostgreSQL does.
