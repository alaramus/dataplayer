from typing import Any
from urllib.parse import unquote

from app.core.config import settings


def working_postgres_options() -> dict[str, Any]:
    """Working connection options for the database started by docker compose.

    DATABASE_URL is a PostgresDsn, that is a multi-host URL: it has no host
    attribute, the parts live in hosts().
    """
    url = settings.DATABASE_URL
    host = url.hosts()[0]
    return {
        # The way of connecting, named: PostgreSQL options are a discriminated
        # union now, and an object that names no variant is refused outright.
        "auth_method": "user_password",
        "host": host["host"] or "localhost",
        "port": host["port"] or 5432,
        "database": (url.path or "/app").lstrip("/"),
        "user": host["username"] or "postgres",
        # PostgresDsn serializes reserved characters in user info. psycopg
        # accepts a password value rather than URL user info, so decode it
        # before handing the options to the adapter.
        "password": unquote(host["password"] or ""),
    }
