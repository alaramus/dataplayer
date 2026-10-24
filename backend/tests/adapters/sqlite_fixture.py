"""The database file the SQLite tests read, written as a person writes one.

Made with a plain connection rather than through the source: the source opens
files defensively, and a fixture has to be able to write what an upload could
bring, a virtual table whose module this server lacks included.
"""

import sqlite3
from pathlib import Path

FILE = "data/shop.db"

SCHEMA = '''
CREATE TABLE labels (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE "items" (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL COLLATE NOCASE CHECK (length(name) > 0),
  price NUMERIC(10,2) DEFAULT 0,
  doubled REAL GENERATED ALWAYS AS (price * 2) STORED,
  label_id INT CONSTRAINT to_label REFERENCES labels ON DELETE CASCADE,
  picture BLOB,
  loose,
  active BOOLEAN DEFAULT 1,
  made_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT positive CHECK (price >= 0),
  UNIQUE (name, price)
);

CREATE INDEX items_expensive ON items (price DESC) WHERE price > 5;
CREATE TRIGGER items_named AFTER INSERT ON items BEGIN SELECT 1; END;

-- No primary key: pages follow the rowid (D251).
CREATE TABLE events (kind TEXT, at INTEGER);

CREATE TABLE "odd, ""name""" ("a b" TEXT, [c] INTEGER, `d` REAL);

CREATE TABLE pairs (
  left_id INTEGER NOT NULL,
  right_id INTEGER NOT NULL,
  PRIMARY KEY (left_id, right_id),
  FOREIGN KEY (left_id) REFERENCES labels
) WITHOUT ROWID;

CREATE VIEW cheap AS SELECT id, name, price FROM items WHERE price < 5;

CREATE VIRTUAL TABLE notes USING fts5(body);
'''

ROWS = """
INSERT INTO labels (name) VALUES ('red'), ('green');
INSERT INTO items (name, price, label_id, picture, loose, active) VALUES
  ('one', 1.5, 1, x'00ff', 10, 1),
  ('two', 2, 2, NULL, 'ten', 0),
  ('100% pure', 9, NULL, NULL, 3.25, 1),
  ('under_score', 12, NULL, NULL, NULL, NULL);
INSERT INTO events (kind, at) VALUES ('b', 1), ('a', 1), ('c', 1), ('a', 2);
INSERT INTO pairs VALUES (1, 2), (2, 1);
INSERT INTO notes (body) VALUES ('hello world');
"""


def build(home: Path) -> Path:
    """The fixture's file inside `home`, made afresh."""
    path = home.joinpath(*FILE.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.executescript(ROWS)
        # Text that is not UTF-8, as another program may have stored it.
        connection.execute("INSERT INTO events (kind, at) VALUES (CAST(x'fffe' AS TEXT), 3)")
        connection.execute("INSERT INTO events (kind, at) VALUES ('big', 9007199254740993)")
        connection.commit()
    finally:
        connection.close()
    return path


def add_ghost(path: Path) -> None:
    """A virtual table whose module no library here has."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA writable_schema = ON")
        connection.execute(
            "INSERT INTO sqlite_schema (type, name, tbl_name, rootpage, sql) "
            "VALUES ('table', 'ghost', 'ghost', 0, "
            "'CREATE VIRTUAL TABLE ghost USING nosuchmodule(x)')"
        )
        connection.commit()
    finally:
        connection.close()


def analyze(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("ANALYZE")
        connection.commit()
    finally:
        connection.close()
