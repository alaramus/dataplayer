from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession


@dataclass(frozen=True)
class TimescaleSource:
    port: int
    version: str
    storage: Literal["heap", "hypercore"]

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
