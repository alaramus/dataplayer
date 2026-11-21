"""The database file the DuckDB tests read, written as a person writes one.

Made with a plain connection rather than through the source: the source opens
files locked to the home, and a fixture has to be able to write a view that
reaches past it, as an upload could bring.
"""

from pathlib import Path

import duckdb

FILE = "data/shop.duckdb"

SCHEMA = r'''
CREATE TYPE mood AS ENUM ('sad', 'ok', 'it''s');
CREATE SCHEMA "sales.eu";

CREATE TABLE labels (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE);

CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  name VARCHAR NOT NULL CHECK (length(name) > 0),
  price DECIMAL(10, 2) DEFAULT 0,
  label_id INTEGER REFERENCES labels (id),
  UNIQUE (name, price)
);
CREATE INDEX items_price ON items (price);
COMMENT ON TABLE items IS 'What the shop sells';

-- No primary key: pages follow the rowid (D391).
CREATE TABLE events (kind VARCHAR, step INTEGER);

CREATE TABLE kinds (
  id INTEGER PRIMARY KEY,
  huge HUGEINT,
  exact DECIMAL(38, 10),
  ratio DOUBLE,
  picture BLOB,
  active BOOLEAN,
  day DATE,
  moment TIMESTAMPTZ,
  span INTERVAL,
  ident UUID,
  feeling mood,
  tags VARCHAR[],
  point STRUCT(x INTEGER, "the label" VARCHAR),
  counts MAP(INTEGER, VARCHAR),
  doc JSON
);

CREATE TABLE "odd, ""name""" ("a b" VARCHAR, rowid INTEGER);

CREATE TABLE "sales.eu".orders (id BIGINT PRIMARY KEY, item INTEGER);

CREATE VIEW cheap AS SELECT id, name, price FROM items WHERE price < 5;
'''

ROWS = r'''
INSERT INTO labels VALUES (1, 'red'), (2, 'green');
INSERT INTO items VALUES
  (1, 'one', 1.5, 1),
  (2, 'two', 2, 2),
  (3, '100% pure', 9, NULL),
  (4, 'under_score', 12, NULL);
INSERT INTO events VALUES ('b', 1), ('a', 1), ('c', 1), ('a', 2);
INSERT INTO kinds VALUES (
  1,
  170141183460469231731687303715884105727,
  12345678901234567890.0123456789,
  0.1,
  '\xAA\x00'::BLOB,
  true,
  '2026-01-02',
  '2026-01-02 03:04:05+03',
  INTERVAL '1 year 2 days 3 hours',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'it''s',
  ['a', NULL],
  {'x': 1, 'the label': 'p'},
  MAP {1: 'one'},
  '{"k": [1, 2.50]}'
);
INSERT INTO kinds (id) VALUES (2);
INSERT INTO "odd, ""name""" VALUES ('x', 7);
INSERT INTO "sales.eu".orders VALUES (10, 1);
'''


def build(home: Path) -> Path:
    """The fixture's file inside `home`, made afresh."""
    path = home.joinpath(*FILE.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    connection = duckdb.connect(str(path))
    try:
        connection.execute(SCHEMA)
        connection.execute(ROWS)
    finally:
        connection.close()
    return path


def add_reaching_view(path: Path, outside: Path) -> None:
    """A view that reads a file outside the home, as an upload could bring."""
    connection = duckdb.connect(str(path))
    try:
        target = outside.as_posix().replace("'", "''")
        # A path the test made, quoted: a view's text takes no placeholders.
        connection.execute(f"CREATE VIEW reaching AS SELECT * FROM read_csv('{target}')")  # noqa: S608
    finally:
        connection.close()
