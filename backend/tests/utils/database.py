from typing import Any

from app.core.config import settings


def working_postgres_options() -> dict[str, Any]:
    """Рабочие параметры подключения к БД, которую поднимает docker compose.

    DATABASE_URL — это PostgresDsn, то есть multi-host URL: атрибута host у него
    нет, параметры лежат в hosts().
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
