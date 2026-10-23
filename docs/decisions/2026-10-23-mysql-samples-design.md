# MySQL sample data

Decision D245. A MySQL or MariaDB server started here (D244) may be filled
with sample data, as a PostgreSQL or TimescaleDB one may.

## The same lab, told in MySQL's words

PostgreSQL's samples are a lab: organizations, their people and teams,
projects, tasks with tags and dependencies, measurements and an audit trail.
The MySQL script tells the same story, so a person comparing the two sources
compares like with like. It is a MySQL script rather than a translation of the
PostgreSQL one, and it shows what MySQL has:

- ENUM and SET columns, JSON, BIT, TIME, fractional timestamps, binary
  values;
- virtual and stored generated columns;
- named checks;
- a table partitioned by year, which therefore has no foreign key, as MySQL
  requires;
- full-text, prefix and spatial keys;
- foreign keys that cascade, restrict and set null;
- a view, a function and a trigger;
- a table with no key, which the grid edits by its values (D242).

Everything in it is in both MySQL 8.4 and MariaDB 11.4, and the suite fills
both. Functional key parts and SRID column attributes are MySQL's alone, and
are left out.

## Its own database

PostgreSQL's samples are a schema of the database the connection opens on.
A MySQL schema is a database (D229), so the lab is a database of its own,
`demo_lab`, beside the one the service was started with. The script drops it
first, so loading it twice is loading it once.

## How it is run

aiomysql runs one statement per call. The script is split where a line ends
in a semicolon. It is written so that only a statement's end does: no trigger
or function body has a semicolon of its own, and comment lines are dropped
before splitting. Each statement is sent without parameters, so a `%` in it is
a character. The script chooses its database with USE, so it runs on a
connection of its own, closed afterwards rather than returned to the pool.
