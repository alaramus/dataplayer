from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession


def release(version: str) -> tuple[int, ...]:
    """A Timescale version as comparable numbers; "2.18.0" sorts before "2.19.3"."""
    return tuple(int(part) for part in version.split("."))


@dataclass(frozen=True)
class TimescaleSource:
    port: int
    version: str
    postgres_major: int
    storage: Literal["heap", "hypercore"]

    def at_least(self, version: str) -> bool:
        return release(self.version) >= release(version)

    def options(
        self, *, database: str = "timescale_fixture", user: str = "fixture_admin",
    ) -> PostgresUserPassword:
        return PostgresUserPassword(
            host="127.0.0.1", port=self.port, database=database,
            user=user, password=SecretStr("fixture-only"),
        )

    def adapter(
        self, *, database: str = "timescale_fixture", user: str = "fixture_admin",
    ) -> PostgresAdapter:
        return PostgresAdapter(self.options(database=database, user=user))

    def session(self, *, database: str = "timescale_fixture") -> PostgresSession:
        return PostgresSession(self.options(database=database))
