"""A database of known shape on each MySQL server the suite talks to.

Built with the driver directly rather than through the adapter, which cannot
write yet, and rebuilt by every module that asks for it.
"""

from dataclasses import dataclass

import aiomysql

from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.options import MysqlUserPassword
from app.adapters.mysql.session import options_from_url
from tests.utils.services import MARIADB, MYSQL, Server

# A dot in the name on purpose: MySQL allows one, and a node id must survive it.
DATABASE = "dp_test.mysql"
OTHER = "dp_test_other"

_SCHEMA = [
    f"DROP DATABASE IF EXISTS `{DATABASE}`",
    f"DROP DATABASE IF EXISTS `{OTHER}`",
    f"CREATE DATABASE `{DATABASE}`",
    f"CREATE DATABASE `{OTHER}`",
    f"CREATE TABLE `{OTHER}`.owners (id INT PRIMARY KEY, name VARCHAR(40) NOT NULL)",
    f"""
    CREATE TABLE `{DATABASE}`.items (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        label VARCHAR(40) NOT NULL DEFAULT 'it''s',
        `100%` INT NULL,
        amount DECIMAL(30,10),
        big BIGINT UNSIGNED,
        flags BIT(3),
        kind ENUM('small','it''s big'),
        payload JSON,
        place POINT,
        raw VARBINARY(8),
        made DATETIME DEFAULT CURRENT_TIMESTAMP,
        seen TIMESTAMP NULL,
        spent TIME,
        day DATE,
        doubled INT AS (`100%` * 2) VIRTUAL,
        owner_id INT,
        UNIQUE KEY items_label (label),
        KEY items_prefix (label(4)),
        CONSTRAINT items_owner FOREIGN KEY (owner_id) REFERENCES `{OTHER}`.owners (id)
            ON DELETE SET NULL,
        CONSTRAINT items_amount CHECK (amount >= 0)
    ) COMMENT 'Things'
    """,
    f"CREATE TABLE `{DATABASE}`.keyless (a INT NOT NULL, b INT, UNIQUE KEY keyless_a (a))",
    f"CREATE TABLE `{DATABASE}`.heap (a INT, b INT)",
    f"CREATE VIEW `{DATABASE}`.item_labels AS SELECT id, label FROM `{DATABASE}`.items",
    f"INSERT INTO `{OTHER}`.owners VALUES (1, 'Ann')",
    f"""
    INSERT INTO `{DATABASE}`.items
        (label, `100%`, amount, big, flags, kind, payload, place, raw, seen, spent, day, owner_id)
    VALUES
        ('alpha', 5, 12345678901234567890.0123456789, 18446744073709551615, b'101',
         'it''s big', '{{"a": [1, 2]}}', ST_GeomFromText('POINT(1 2)'), X'00FF',
         '2024-01-02 03:04:05', '-12:30:00', '2024-02-03', 1),
        ('50% off', NULL, 0, 1, b'000', 'small', NULL, NULL, NULL, NULL, '100:00:01', NULL, NULL),
        ('under_score', 1, 1, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
    """,
    f"INSERT INTO `{DATABASE}`.keyless VALUES (3, 1), (1, 2), (2, 3)",
]


@dataclass(frozen=True)
class Target:
    server: Server
    flavour: str

    def options(self, **override: object) -> MysqlUserPassword:
        values = {**options_from_url(self.server.require()), **override}
        return MysqlUserPassword(**values)

    def adapter(self, **override: object) -> MysqlAdapter:
        return MysqlAdapter(self.options(**override))


TARGETS = [Target(MYSQL, "mysql"), Target(MARIADB, "mariadb")]


async def run(target: Target, *statements: str) -> None:
    options = target.options()
    connection = await aiomysql.connect(
        host=options.host,
        port=options.port,
        user=options.user,
        password=options.password.get_secret_value(),
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            for statement in statements:
                await cursor.execute(statement)
    finally:
        connection.close()


async def build(target: Target) -> None:
    await run(target, *_SCHEMA)


async def tear_down(target: Target) -> None:
    await run(target, f"DROP DATABASE IF EXISTS `{DATABASE}`", f"DROP DATABASE IF EXISTS `{OTHER}`")
