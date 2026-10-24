# Changing MySQL structure

Decision D235. The first half of the fourth slice of the MySQL source:
columns, indexes and constraints changed from the structure screen. Designing
a new table and making one from rows follow in the second half.

## MODIFY keeps nothing it is not told

PostgreSQL changes one property of a column at a time: `ALTER COLUMN … TYPE`,
`SET NOT NULL`. MySQL changes a type or nullability with
`MODIFY COLUMN name <definition>`, and the definition replaces the old one
whole. A definition rebuilt from `information_schema` has to restate the type,
the character set, the collation, NULL, the default (an expression or a
literal, spelled differently on the two servers), AUTO_INCREMENT, ON UPDATE,
INVISIBLE, the comment and the SRID. Anything the rebuild forgets is dropped
without a word. Losing a default or an AUTO_INCREMENT on a nullability change
is a known failure of tools that rebuild.

`SHOW CREATE TABLE` prints the definition the server would use to recreate
the column. Taking that line and replacing only the type, or only the NULL
marker, keeps everything else by construction. The replacement is found by
sqlglot's MySQL tokens rather than by text search, so `'NOT NULL'` inside a
comment or an enum label is a string and not a keyword. The tokens are also
what decide where the type ends: a character set and a collation belong to
the type, since MySQL takes them before NOT NULL.

## Strict mode, and counting what a type refuses

In the server's default mode a `MODIFY` to a narrower type does not fail on a
value it cannot hold: it stores the nearest one and leaves a warning. Every
structure change therefore runs with STRICT_ALL_TABLES added to the session's
mode, restored afterwards, as row changes do (D234).

D38 answers a refused type change with a count. PostgreSQL counts string
columns before trying, with `pg_input_is_valid`. MySQL has no such function
and no TRY_CAST. The change is tried in strict mode. Only if it is refused is
the column copied with `INSERT IGNORE` into a temporary column of the new
type, where each refused value becomes a warning, and `@@warning_count` is the
count. aiomysql reads SHOW WARNINGS itself after any statement that left one,
which resets the count, so this one statement uses a cursor that does not.
Counting only after a refusal means a change that succeeds scans the table
once.

## Names and objects

The server names what it makes: an index after its first column, a foreign
key `<table>_ibfk_<n>`. No name is asked of the person, for D39's reason, and
the new name is read back from the table.

MySQL has no unique constraint apart from a unique index, so the two are one
object. The structure screen still shows a unique key among the constraints
and the indexes, as the catalog does. It is dropped through the constraint, as
PostgreSQL's index behind a constraint is.

The rest are smaller rules:

- InnoDB parses `ON DELETE SET DEFAULT` and does not carry it out, so it is
  refused rather than accepted.
- A check is dropped with `DROP CHECK` on MySQL and `DROP CONSTRAINT` on
  MariaDB, which is where the two grammars differ.
- HASH is not offered as an index method: InnoDB builds a B-tree when asked
  for one, and a method shown that was not built is a lie on the screen.

## Vocabulary

The type list is MySQL's own rather than PostgreSQL's mapped across, since a
person choosing a type for a MySQL column thinks in MySQL's types:

- text as `varchar(255)`, long text as `text`;
- integer, big integer, `decimal(20,6)` and double;
- boolean as `tinyint(1)`;
- date, datetime and timestamp;
- JSON, and a UUID as `char(36)`.

MariaDB accepts the same spellings. Its `json` is LONGTEXT with a check, which
the catalog reads back as JSON (D228).
