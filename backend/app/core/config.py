import base64
import warnings
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    EmailStr,
    Field,
    PostgresDsn,
    SecretStr,
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
    # Encrypts what is said in a conversation with the agent and the model's
    # working state, for the reason query content has a key of its own (D141).
    AI_CONTENT_KEY: str

    @field_validator(
        "CONNECTOR_SECRET_KEY",
        "QUERY_CONTENT_KEY",
        "AI_CONTENT_KEY",
        "DATA_CACHE_SECRET_KEY",
    )
    @classmethod
    def _validate_encryption_key(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        """Every supplied AES-GCM key is checked by the same rule."""
        if value is None:
            return None
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

    # Where each process keeps its log as a file of JSON lines, rotated by
    # size, beside standard output. Unset keeps standard output alone (D184).
    LOG_DIR: Path | None = None
    LOG_FILE_MAX_BYTES: int = Field(default=10 * 1024 * 1024, ge=64 * 1024)
    # Files per process, the one being written included.
    LOG_FILE_COUNT: int = Field(default=5, ge=1, le=50)

    # Ceiling for one upload, counted as the bytes arrive: the length a client
    # declares is a claim, not a fact.
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024
    # Transfers between connections one person may have running at once (D168).
    TRANSFER_MAX_ACTIVE: int = 3
    # Pipelines one person may have running at once (D177).
    PIPELINE_MAX_ACTIVE: int = 3
    # How often the server looks for pipelines whose schedule has come (D179).
    SCHEDULE_TICK_SECONDS: int = 30
    # How long converting a table with rows into a hypertable may run before it
    # is rolled back (D207). The table is locked against reads and writes for
    # all of it.
    TIMESCALE_CONVERSION_TIMEOUT_SECONDS: int = Field(default=3600, gt=0, le=86400)

    # What one answer of the search may spend (D200). While typing, one
    # deadline for everything; on Enter, each cheap cell, each costly cell and
    # all of them together.
    SEARCH_TYPING_SECONDS: float = Field(default=0.4, gt=0, le=2)
    SEARCH_CHEAP_SECONDS: float = Field(default=2.0, gt=0, le=10)
    SEARCH_COSTLY_SECONDS: float = Field(default=10.0, gt=0, le=30)
    SEARCH_TOTAL_SECONDS: float = Field(default=20.0, gt=0, le=60)
    # Connections one answer asks at most, and at once.
    SEARCH_MAX_CONNECTIONS: int = Field(default=20, ge=1, le=100)
    SEARCH_PARALLEL_CONNECTIONS: int = Field(default=4, ge=1, le=16)
    # Worker threads the search may hold, apart from every other route's.
    SEARCH_THREADS: int = Field(default=4, ge=1, le=16)
    # Keys a Redis server may hold and still be searched while somebody types:
    # a scan looks at every key whatever matches.
    SEARCH_CHEAP_KEYS: int = Field(default=20_000, ge=0, le=1_000_000)
    # A search inside files, as a job (S7): how long it may run over every
    # connection chosen, and how long its words and matches are held in
    # memory once it ends.
    SEARCH_CONTENTS_SECONDS: float = Field(default=600.0, gt=0, le=3600)
    SEARCH_CONTENTS_HELD_SECONDS: float = Field(default=1800.0, gt=0, le=7200)
    # A kept list of names (D213): how many one connection keeps at most, and
    # how long one pass over it may take.
    SEARCH_KEPT_MAX_NAMES: int = Field(default=200_000, ge=1, le=2_000_000)
    SEARCH_KEPT_PASS_SECONDS: float = Field(default=900.0, gt=0, le=7200)
    # What one pass over a connection's kept text may read (D218): the rest
    # is read by the next.
    SEARCH_KEPT_CONTENTS_BYTES: int = Field(default=512_000_000, ge=1, le=20_000_000_000)
    # Search by meaning (D220): where the local model answers, empty for off;
    # what it expects before a query and a passage (e5's two by default); how
    # close a passage must be to be offered.
    EMBEDDINGS_URL: str = ""
    EMBEDDINGS_QUERY_PREFIX: str = "query: "
    EMBEDDINGS_PASSAGE_PREFIX: str = "passage: "
    EMBEDDINGS_MIN_SIMILARITY: float = Field(default=0.8, ge=0, le=1)

    # Connections a source keeps between requests. Per process: every worker
    # has its own pools, so a server with four workers may hold four times
    # POOL_MAX_SIZE connections to one database.
    POOL_MAX_SIZE: int = 5
    POOL_MAX_POOLS: int = 20
    POOL_MAX_IDLE_SECONDS: float = 300.0

    # Exact catalog levels and bounded fetch pages: per process in memory, or
    # per deployment in Redis. A source chooses its own TTL independently.
    DATA_CACHE_MAX_ENTRIES: int = Field(default=512, ge=1)
    # Memory is the correctness baseline. Redis is an optional shared
    # accelerator and needs all three values before it can be selected (D103).
    DATA_CACHE_BACKEND: Literal["memory", "redis"] = "memory"
    DATA_CACHE_REDIS_URL: SecretStr | None = None
    DATA_CACHE_DEPLOYMENT: str = Field(
        default="default",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$",
    )
    DATA_CACHE_SECRET_KEY: str | None = None
    DATA_CACHE_REDIS_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0, le=30)

    @field_validator("DATA_CACHE_REDIS_URL")
    @classmethod
    def _validate_cache_redis_url(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value.get_secret_value())
            valid = parsed.scheme in {"redis", "rediss"} and bool(parsed.hostname)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("DATA_CACHE_REDIS_URL must be a redis:// or rediss:// URL")
        return value

    @model_validator(mode="after")
    def _require_shared_cache_settings(self) -> Self:
        if self.DATA_CACHE_BACKEND == "redis":
            missing = [
                name
                for name, value in (
                    ("DATA_CACHE_REDIS_URL", self.DATA_CACHE_REDIS_URL),
                    ("DATA_CACHE_SECRET_KEY", self.DATA_CACHE_SECRET_KEY),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required when DATA_CACHE_BACKEND=redis"
                )
        return self

    # Whether this installation may start containers of its own, and where the
    # runtime that would do it listens. Off unless a deployment says otherwise:
    # reaching a container runtime is reaching the machine, and the threat
    # model for that is the last item of the phase that introduced this.
    SERVICES_ENABLED: bool = False
    DOCKER_SOCKET: str = "/var/run/docker.sock"
    # The container network a service joins, which is how this server reaches
    # it: a connector made from a service names the container, and a name is
    # resolvable only on a network they share. Without one a service could be
    # started and not used, so the offer says so instead.
    SERVICE_NETWORK: str = ""
    # What one service may take of the machine. A container with no limits can
    # take all of it, and a person starting a database is not asking for that
    # (D86). Memory in mebibytes, processors as a fraction, and a ceiling on
    # processes because a fork bomb needs neither of the other two.
    SERVICE_MEMORY_MB: int = 1024
    SERVICE_CPUS: float = 1.0
    SERVICE_PIDS_LIMIT: int = 512
    # How many one person may have at once. Not a quota system: a number that
    # turns "somebody left a loop running" from an outage into a refusal.
    SERVICE_MAX_PER_USER: int = 5
    # The named volume personal storage lives in, so that a program run in
    # a container of its own can write a backup where its owner will find
    # it. Without one, backups are not offered: a dump written inside a
    # container that is then thrown away is worse than a refusal (D87).
    SERVICE_STORAGE_VOLUME: str = ""

    # Where the metrics process listens for agent datagrams (D127). The web
    # process never binds it.
    METRICS_UDP_HOST: str = "0.0.0.0"
    METRICS_UDP_PORT: int = 9999
    # Development only: the key of an agent seeded for the first superuser, so
    # the agent in the Compose profile can report without a screen to issue one.
    METRICS_DEV_AGENT_KEY: SecretStr | None = None

    # How long a socket may stay open without saying who it is. A socket that
    # says nothing still holds a connection.
    WS_AUTH_TIMEOUT_SECONDS: float = 5.0

    # Watching a user's connections. The monitor reads these every round, so
    # they can be changed under a running one.
    #
    # How often the monitor comes round, which is not how often a connection
    # is probed: that is the user's own choice, and this is the shortest one
    # offered — the tick a change of mind is noticed on.
    HEALTH_INTERVAL_SECONDS: float = 15.0
    HEALTH_BACKOFF_CAP_SECONDS: float = 120.0
    HEALTH_PROBE_TIMEOUT_SECONDS: float = 5.0
    HEALTH_CONCURRENCY: int = 8
    # A reloaded page closes one socket and opens another; without this the
    # monitor would be rebuilt from knowing nothing every time.
    HEALTH_GRACE_SECONDS: float = 5.0

    # A deleted query document waits this long before its body is gone for
    # good, and the sweep that removes the expired ones runs this often. D63.
    QUERY_HISTORY_SWEEP_SECONDS: float = 3600.0
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
    # How long a manual transaction may sit idle before rollback (D66).
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

    # How long one answer of the agent may take before it is stopped (D137).
    AI_RUN_TIMEOUT_SECONDS: float = 900.0
    # The most one answer may write, whatever the model could produce: a
    # runaway answer is paid for by whoever owns the key.
    AI_MAX_OUTPUT_TOKENS: int = 16_000
    # Older turns are summarised when a conversation nears the chosen model's
    # context window — this fraction of it (D139). The window itself comes from
    # the curated models file (D140).
    AI_SUMMARY_TRIGGER_FRACTION: float = 0.8
    # Newest messages kept verbatim when older turns are summarised.
    AI_SUMMARY_KEEP_MESSAGES: int = 20
    # Connections the model's working state may hold in the application
    # database (D139).
    AI_CHECKPOINT_POOL_SIZE: int = 4

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
