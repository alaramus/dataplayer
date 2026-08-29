import base64
import warnings
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    EmailStr,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # Encrypts connector credentials. Deliberately separate from SECRET_KEY:
    # rotating SECRET_KEY only logs everyone out, while rotating this key
    # requires migrating the stored secrets.
    CONNECTOR_SECRET_KEY: str

    @field_validator("CONNECTOR_SECRET_KEY")
    @classmethod
    def _validate_connector_secret_key(cls, value: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(value)
        except Exception:
            raise ValueError("CONNECTOR_SECRET_KEY must be urlsafe base64") from None
        if len(raw) != 32:
            raise ValueError("CONNECTOR_SECRET_KEY must decode to exactly 32 bytes")
        return value

    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    DATABASE_URL: PostgresDsn

    # Holds one directory per user. A file connector can only ever reach
    # inside the directory of its owner.
    USER_STORAGE_ROOT: Path = Path("/data/users")

    # Ceiling for one upload, counted as the bytes arrive: the length a client
    # declares is a claim, not a fact.
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024

    # Connections a source keeps between requests. Per process: every worker
    # has its own pools, so a server with four workers may hold four times
    # POOL_MAX_SIZE connections to one database.
    POOL_MAX_SIZE: int = 5
    POOL_MAX_POOLS: int = 20
    POOL_MAX_IDLE_SECONDS: float = 300.0

    # Exact catalog levels and bounded fetch pages kept per backend process.
    # A source opts in and chooses its own TTL; this only bounds memory.
    DATA_CACHE_MAX_ENTRIES: int = 512

    # How long a socket may stay open without saying who it is. A socket that
    # says nothing still holds a connection.
    WS_AUTH_TIMEOUT_SECONDS: float = 5.0

    # Watching a user's connections. The monitor reads these every round, so
    # they can be changed under a running one.
    HEALTH_INTERVAL_SECONDS: float = 15.0
    HEALTH_BACKOFF_CAP_SECONDS: float = 120.0
    HEALTH_PROBE_TIMEOUT_SECONDS: float = 5.0
    HEALTH_CONCURRENCY: int = 8
    # A reloaded page closes one socket and opens another; without this the
    # monitor would be rebuilt from knowing nothing every time.
    HEALTH_GRACE_SECONDS: float = 5.0

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
