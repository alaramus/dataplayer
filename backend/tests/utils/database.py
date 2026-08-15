from typing import Any

from app.core.config import settings


def working_postgres_options() -> dict[str, Any]:
    """Working connection options for the database started by docker compose.

    DATABASE_URL is a PostgresDsn, that is a multi-host URL: it has no host
    attribute, the parts live in hosts().
    """
    url = settings.DATABASE_URL
    host = url.hosts()[0]
    return {
        "host": host["host"] or "localhost",
        "port": host["port"] or 5432,
        "database": (url.path or "/app").lstrip("/"),
        "user": host["username"] or "postgres",
        "password": host["password"] or "",
    }
