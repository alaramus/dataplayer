# Copying MySQL tables

Decision D239. The first part of the sixth slice of the MySQL source: Copy
tables (D182) between MySQL and MariaDB connections.

## One dialect for both servers

The copy contract joins two ends of one dialect. MySQL and MariaDB print
tables in nearly the same words, and the source type is already one for both
(D228), so the dialect is one as well: `mysql`. Where one server does not know
a word of the other's, the destination refuses the statement and says which
step it was. The suite pins the one direction that fails today: MariaDB's
default collation, `utf8mb4_uca1400_ai_ci`, is unknown to MySQL 8.4, while
MariaDB 11.4 knows MySQL's.

Two dialects would make every copy between the servers a refusal before it
starts, for the sake of the cases that fail anyway.

## The description is what the server prints

PostgreSQL's description is built from its catalog, field by field, because
`pg_catalog` keeps every part apart and prints each with a function of its own.
MySQL's `information_schema` does not: a column's default is printed
differently by each server, ON UPDATE is a word in `EXTRA`, a character set
is two more columns, a key's prefix length and a functional key part are
fragments in `STATISTICS`. Rebuilding a column from them is the same rebuild
the structure changes rejected (D235), and it loses what it forgets.

So the source sends the lines `SHOW CREATE TABLE` prints:

- every column's definition after its name;
- the primary key, the unique keys and the indexes, a line each;
- the checks without their names;
- the table's options without `AUTO_INCREMENT=`. The copy numbers on from the
  rows it is given, as any MySQL table does.

The shared description gained two optional fields for this: a column's whole
`definition` and the table's `options`. The fields PostgreSQL fills are read
off the definition for the window.

Foreign keys travel as links, field by field, because the window decides for
each whether it points at a copy, at the original, or nowhere.

## A printed line is checked before it is composed

A destination does not run text it did not write without checking it. Each
line goes through MySQL's own tokenizer, and it must hold:

- no semicolon;
- no comment, a `/*!…*/` included, since MySQL runs those;
- every parenthesis closed.

A column that fails makes the table a problem; a key, an index or the options
that fail are left out with a warning. A line that names something with a `%`
is shown as it is and doubled only when sent, since every statement goes with
parameters.

## Not one transaction

PostgreSQL makes the copy in one transaction. MySQL commits CREATE TABLE and
ALTER TABLE by themselves (D233), so the copy runs in three steps:

1. the tables, each committed as it is made;
2. the rows of every table in one transaction, in strict mode;
3. the links, each an ALTER TABLE that checks the rows it joins.

Any failure, and a Stop, drops the tables this copy made, with foreign key
checks off for that one statement. Nothing else had those tables yet: they
were not there when the copy was planned, and the plan refuses a name that
is taken.

## Rows as JSON lines

PostgreSQL's rows travel in COPY's text format, which both ends speak. MySQL
has nothing like it that a client can rely on: `LOAD DATA LOCAL` is off by
default on MySQL 8. So the rows travel as JSON lines, one array of text per
row, and arrive in INSERTs of many rows of about a megabyte each.

Each value is read as text the server reads back the same:

- a date, a time, a timestamp and JSON as the server casts them to text, so a
  zero date, a fraction and a negative or long TIME survive;
- binary values and shapes as the hexadecimal of their stored bytes, written
  back through UNHEX;
- a BIT as its number, since a BIT given a string takes the bytes of its
  characters;
- everything else as the driver reads it, a float by its shortest exact text.

Both ends work in UTC (D230), so a TIMESTAMP arrives at the same instant.
NO_AUTO_VALUE_ON_ZERO is set while the rows arrive, because a zero in an
AUTO_INCREMENT column is a value of the source's, not a request for the next
number.

The rows of every table are read in one `START TRANSACTION WITH CONSISTENT
SNAPSHOT`, on a connection of their own that is closed afterwards.

## Names

A check and a link are renamed after the copy, as PostgreSQL's are:
`items_amount` becomes `items_copy_amount`. MySQL wants a check and a foreign
key name once in a database, so a name already there gets a number. An index
name belongs to its table and is kept.
