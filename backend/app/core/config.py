import base64
import warnings
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    EmailStr,
    PostgresDsn,
    ValidationInfo,
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
    # Encrypts what somebody writes in a query document, and later the text an
    # execution ran. Independent of the two keys above for the reason they are
    # independent of each other: the three protect different things and are
    # rotated by different procedures. See D63.
    QUERY_CONTENT_KEY: str

    @field_validator("CONNECTOR_SECRET_KEY", "QUERY_CONTENT_KEY")
    @classmethod
    def _validate_encryption_key(cls, value: str, info: ValidationInfo) -> str:
        """Both keys are AES-GCM keys, so both are checked by the same rule."""
        try:
            raw = base64.urlsafe_b64decode(value)
        except Exception:
            raise ValueError(f"{info.field_name} must be urlsafe base64") from None
        if len(raw) != 32:
            raise ValueError(f"{info.field_name} must decode to exactly 32 bytes")
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

    # Whether this installation may start containers of its own, and where the
    # runtime that would do it listens. Off unless a deployment says otherwise:
    # reaching a container runtime is reaching the machine, and the threat
    # model for that is the last item of the phase that introduced this.
    SERVICES_ENABLED: bool = False
    DOCKER_SOCKET: str = "/var/run/docker.sock"

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

    # A deleted query document waits this long before its body is gone for
    # good, and the sweep that removes the expired ones runs this often. D63.
    QUERY_TRASH_DAYS: int = 30
    QUERY_TRASH_SWEEP_SECONDS: float = 3600.0
    # One document, and the whole library one search may decrypt. The first is
    # D64's ceiling; the second is why the search builds no index: it reads a
    # bounded number of bodies in memory and nothing else.
    QUERY_DOCUMENT_MAX_BYTES: int = 1024 * 1024
    QUERY_SEARCH_MAX_DOCUMENTS: int = 500

    # What one run is held to. Every number here is a boundary D64 states:
    # input bounds first, then time, then how much of a result may be kept.
    QUERY_MAX_STATEMENTS: int = 100
    QUERY_STATEMENT_MAX_BYTES: int = 256 * 1024
    QUERY_SCRIPT_TIMEOUT_SECONDS: int = 600
    QUERY_RESULT_MAX_ROWS: int = 10_000
    QUERY_RESULT_MAX_BYTES: int = 32 * 1024 * 1024
    QUERY_CELL_MAX_BYTES: int = 4 * 1024 * 1024
    QUERY_RUN_MAX_RESULTS: int = 20
    QUERY_RUN_MAX_BYTES: int = 64 * 1024 * 1024
    QUERY_RUN_MAX_MESSAGES: int = 1000
    # A browser asks for a hundred rows of a snapshot and never more than five
    # hundred.
    QUERY_PAGE_DEFAULT_ROWS: int = 100
    QUERY_PAGE_MAX_ROWS: int = 500
    # How long finished runs are kept by default, the ceiling above whatever
    # anybody chooses, and how many a search may decrypt in memory (D63).
    QUERY_HISTORY_DEFAULT_DAYS: int = 90
    QUERY_HISTORY_MAX_RUNS: int = 1000
    QUERY_HISTORY_SEARCH_MAX: int = 500
    # How long an unlock survives without being used, and how long a manual
    # transaction may sit idle before it is rolled back (D66).
    QUERY_UNLOCK_IDLE_MINUTES: int = 15
    QUERY_TRANSACTION_IDLE_SECONDS: float = 300.0
    QUERY_TRANSACTION_SWEEP_SECONDS: float = 10.0
    QUERY_MAX_TRANSACTIONS: int = 3
    # Runs one person may have in flight at once. Excess is refused rather than
    # queued where nobody can see it.
    QUERY_MAX_ACTIVE_RUNS: int = 3
    # Captured results are kept in this process, bounded by bytes and by how
    # long ago each was last read.
    QUERY_RESULT_STORE_MAX_BYTES: int = 256 * 1024 * 1024
    QUERY_RESULT_TTL_SECONDS: float = 1800.0

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
