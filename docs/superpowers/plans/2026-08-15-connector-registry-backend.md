# План реализации: реестр коннекторов, бэкенд

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API, позволяющий создать коннектор к PostgreSQL, сохранить его учётные данные зашифрованными и проверить соединение.

**Architecture:** Типы источников описаны реестром в коде: класс драйвера и Pydantic-схема опций рядом друг с другом. В БД лежит только `Connector`, где несекретные поля хранятся в jsonb, а секретные — отдельным зашифрованным полем; разделение выполняется автоматически по типу `SecretStr` в схеме. Контракт адаптера — `typing.Protocol` с единственным методом `check_connection()`, который никогда не выпускает наружу исключение драйвера.

**Tech Stack:** Python 3.14, FastAPI, SQLModel поверх SQLAlchemy 2 в асинхронном режиме, psycopg 3 (async), Alembic, PostgreSQL, pytest + pytest-asyncio, cryptography (AES-GCM), uv.

Спек: [2026-08-15-connector-registry-design.md](../specs/2026-08-15-connector-registry-design.md)

## Global Constraints

- Python 3.14; зависимости ставятся через `uv`, запуск команд — через `uv run`.
- `uv run mypy app` (режим strict, задан в `pyproject.toml`) и `uv run ruff check app tests` проходят без ошибок после каждой задачи.
- Все ручки живут под префиксом `/api/v1` (значение `settings.API_V1_STR`).
- Секреты никогда не попадают в ответы API, в тексты ошибок и в логи.
- Таймаут проверки соединения — ровно 5 секунд.
- Ключ шифрования — переменная `CONNECTOR_SECRET_KEY`, отдельная от `SECRET_KEY`.
- Новый код размещается модулями (`app/adapters/`, `app/connectors/`). Плоские `app/models.py`, `app/crud.py` и `app/api/routes/` в этом плане только переводятся на async, без перемещения (решение Р5 спека).
- Перед запуском тестов должна быть поднята БД: `docker compose up -d db`.
- **На Windows** psycopg 3 в асинхронном режиме несовместим с `ProactorEventLoop`, который Python выбирает по умолчанию, и падает с `InterfaceError`. Цикл создаётся через `app.core.db.loop_factory` — она подключена к стартовым скриптам и к pytest-asyncio (фикстура `_asyncio_loop_factory` в `tests/conftest.py`). Политики циклов для этого не годятся: в Python 3.14 они объявлены устаревшими. В Linux-контейнере фабрика возвращает обычный цикл.
- Любой блокирующий вызов в async-ручке останавливает весь цикл событий. `send_email` работает по SMTP синхронно, поэтому вызывается через `starlette.concurrency.run_in_threadpool`. То же правило действует для любого нового блокирующего кода.

---

### Task 1: Привести бэкенд в рабочее состояние и перевести на async

Бэкенд сейчас не импортируется из-за синтаксической ошибки, а установленное окружение отстаёт от `pyproject.toml`. Задача чинит это и переводит весь бэкенд на асинхронный доступ к БД. Критерий готовности — существующий набор тестов проходит целиком.

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/main.py:12,37`
- Modify: `backend/app/core/db.py`
- Modify: `backend/app/crud.py`
- Modify: `backend/app/api/routes/login.py`, `users.py`, `items.py`, `utils.py`, `private.py`
- Modify: `backend/app/backend_pre_start.py`, `backend/app/initial_data.py`, `backend/app/tests_pre_start.py`
- Modify: `backend/tests/conftest.py`, `backend/tests/utils/user.py`, `backend/tests/utils/item.py`, `backend/tests/utils/utils.py`
- Modify: `backend/tests/api/routes/test_login.py`, `test_users.py`, `test_items.py`, `test_private.py`
- Modify: `backend/tests/crud/test_user.py`, `backend/tests/scripts/test_backend_pre_start.py`, `backend/tests/scripts/test_test_pre_start.py`

**Interfaces:**
- Consumes: ничего (первая задача).
- Produces:
  - `app.core.db.engine: AsyncEngine`
  - `app.core.db.async_session_maker: async_sessionmaker[AsyncSession]`
  - `app.core.db.init_db(session: AsyncSession) -> None`
  - `app.api.deps.SessionDep = Annotated[AsyncSession, Depends(get_db)]`
  - `app.api.deps.CurrentUser = Annotated[User, Depends(get_current_user)]`
  - все функции `app.crud` становятся `async def` с теми же именами и параметрами
  - фикстура `client` в тестах — `httpx.AsyncClient`, а не `TestClient`

- [ ] **Step 1: Починить синтаксическую ошибку в deps.py**

В `backend/app/api/deps.py:36` заменить строку

```python
    except InvalidTokenError, ValidationError:
```

на

```python
    except (InvalidTokenError, ValidationError):
```

- [ ] **Step 2: Убедиться, что файл компилируется**

Run: `cd backend && python -m py_compile app/api/deps.py && echo OK`
Expected: `OK` без трассировки.

- [ ] **Step 3: Убрать раздачу фронтенда из main.py**

`app.frontend()` бросает `RuntimeError`, если директории не существует, а `backend/app/frontend` появляется только после первой сборки фронтенда — из-за этого приложение не импортируется, в том числе в тестах. Фронтенд переезжает на Vue и в разработке работает на своём порту, поэтому раздача возвращается позже, в задаче 8 плана фронтенда, уже с проверкой существования директории. Удалить из `backend/app/main.py` строку 12

```python
FRONTEND_DIR = Path(__file__).parent / "frontend"
```

последнюю строку файла

```python
app.frontend("/", directory=FRONTEND_DIR)
```

и ставший ненужным импорт в строке 1

```python
from pathlib import Path
```

- [ ] **Step 4: Добавить зависимости**

В `backend/pyproject.toml` в список `dependencies` добавить:

```toml
    "cryptography>=44.0.0,<47.0.0",
```

В `[dependency-groups]` в список `dev` добавить:

```toml
    "pytest-asyncio>=1.0.0,<2.0.0",
```

В конец файла добавить настройку pytest (сейчас секции `[tool.pytest.ini_options]` в файле нет):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
```

- [ ] **Step 5: Синхронизировать окружение**

Run: `cd backend && uv sync`
Expected: устанавливаются `cryptography` и `pytest-asyncio`.

Все команды запускаются через `uv run`: голый `python` в этом репозитории берёт другое окружение, с другими версиями пакетов.

- [ ] **Step 6: Перевести core/db.py на асинхронный движок**

Полностью заменить содержимое `backend/app/core/db.py`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

engine = create_async_engine(str(settings.DATABASE_URL))

# expire_on_commit=False обязателен: иначе обращение к полю объекта после
# commit() запускает ленивую загрузку, которая в async-режиме падает.
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly


async def init_db(session: AsyncSession) -> None:
    # Tables should be created with Alembic migrations
    result = await session.exec(select(User).where(User.email == settings.FIRST_SUPERUSER))
    user = result.first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = await crud.create_user(session=session, user_create=user_in)
```

- [ ] **Step 7: Перевести deps.py на AsyncSession**

Полностью заменить содержимое `backend/app/api/deps.py`:

```python
from collections.abc import AsyncGenerator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = await session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
```

- [ ] **Step 8: Перевести crud.py на async**

Полностью заменить содержимое `backend/app/crud.py`:

```python
import uuid
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models import Item, ItemCreate, User, UserCreate, UserUpdate


async def create_user(*, session: AsyncSession, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


async def update_user(
    *, session: AsyncSession, db_user: User, user_in: UserUpdate
) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def get_user_by_email(*, session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    return result.first()


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


async def authenticate(
    *, session: AsyncSession, email: str, password: str
) -> User | None:
    db_user = await get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user
        # doesn't exist
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
    return db_user


async def create_item(
    *, session: AsyncSession, item_in: ItemCreate, owner_id: uuid.UUID
) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    await session.commit()
    await session.refresh(db_item)
    return db_item
```

- [ ] **Step 9: Перевести ручки на async**

В файлах `backend/app/api/routes/login.py`, `users.py`, `items.py`, `utils.py`, `private.py` применить механическое преобразование. Правила, применяемые к каждой функции-обработчику:

1. `def handler(...)` → `async def handler(...)`.
2. Каждый вызов функции из `app.crud` получает `await`: `crud.create_user(...)` → `await crud.create_user(...)`.
3. `session.exec(statement)` → `result = await session.exec(statement)`, далее `result.all()` / `result.one()` / `result.first()` вместо `session.exec(statement).all()` и т. п.
4. `session.get(Model, id)` → `await session.get(Model, id)`.
5. `session.commit()` → `await session.commit()`; `session.refresh(obj)` → `await session.refresh(obj)`; `session.delete(obj)` → `await session.delete(obj)`.
6. `session.add(obj)` остаётся без `await` — это синхронная операция.

Пример преобразования для `read_items` в `items.py`:

```python
@router.get("/", response_model=ItemsPublic)
async def read_items(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve items.
    """

    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(Item)
        count = (await session.exec(count_statement)).one()
        statement = (
            select(Item).order_by(col(Item.created_at).desc()).offset(skip).limit(limit)
        )
        items = (await session.exec(statement)).all()
    else:
        count_statement = (
            select(func.count())
            .select_from(Item)
            .where(Item.owner_id == current_user.id)
        )
        count = (await session.exec(count_statement)).one()
        statement = (
            select(Item)
            .where(Item.owner_id == current_user.id)
            .order_by(col(Item.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
        items = (await session.exec(statement)).all()

    return ItemsPublic(data=items, count=count)
```

Функция `get_current_active_superuser` в `deps.py` остаётся синхронной — она не обращается к БД, и FastAPI корректно работает с синхронной зависимостью.

- [ ] **Step 10: Перевести стартовые скрипты на async**

В `backend/app/backend_pre_start.py` и `backend/app/tests_pre_start.py` функция `init` открывает сессию и выполняет `session.exec(select(1))`. Заменить тело на асинхронное и запускать через `asyncio.run`. Для `backend_pre_start.py`:

```python
import asyncio
import logging

from sqlalchemy import Engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

from app.core.db import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
async def init() -> None:
    try:
        async with async_session_maker() as session:
            # Try to create session to check if DB is awake
            await session.exec(select(1))
    except Exception as e:
        logger.error(e)
        raise e


async def main() -> None:
    logger.info("Initializing service")
    await init()
    logger.info("Service finished initializing")


if __name__ == "__main__":
    asyncio.run(main())
```

Неиспользуемый импорт `Engine` удалить. Для `tests_pre_start.py` выполнить то же преобразование, сохранив его собственные тексты сообщений.

В `backend/app/initial_data.py` заменить тело на:

```python
import asyncio
import logging

from app.core.db import async_session_maker, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Creating initial data")
    async with async_session_maker() as session:
        await init_db(session)
    logger.info("Initial data created")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 11: Перевести conftest.py на асинхронные фикстуры**

Полностью заменить содержимое `backend/tests/conftest.py`:

```python
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker, init_db
from app.main import app
from app.models import Item, User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
async def db() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        await init_db(session)
        yield session
        await session.execute(delete(Item))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture(scope="session")
async def client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(scope="session")
async def superuser_token_headers(client: AsyncClient) -> dict[str, str]:
    return await get_superuser_token_headers(client)


@pytest.fixture(scope="session")
async def normal_user_token_headers(
    client: AsyncClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
```

Область видимости фикстур `client`, `superuser_token_headers` и `normal_user_token_headers` меняется с `module` на `session`, чтобы совпасть с областью цикла событий, заданной в `asyncio_default_fixture_loop_scope`.

- [ ] **Step 12: Перевести тестовые утилиты и тесты на async**

В `backend/tests/utils/user.py`, `backend/tests/utils/item.py`, `backend/tests/utils/utils.py` и во всех файлах `backend/tests/api/routes/*.py`, `backend/tests/crud/test_user.py`, `backend/tests/scripts/*.py` применить преобразование:

1. Каждая тестовая функция и каждая вспомогательная функция, обращающаяся к БД или к клиенту, становится `async def`.
2. `client.get(...)`, `client.post(...)`, `client.patch(...)`, `client.delete(...)` получают `await`.
3. Вызовы `crud.*` получают `await`.
4. `db.exec(...)`, `db.get(...)`, `db.commit()`, `db.refresh(...)`, `db.delete(...)` получают `await`.
5. Аннотации типов `Session` → `AsyncSession` с импортом `from sqlmodel.ext.asyncio.session import AsyncSession`.
6. Аннотации типов `TestClient` → `AsyncClient` с импортом `from httpx import AsyncClient`.
7. В `backend/tests/scripts/test_backend_pre_start.py` и `test_test_pre_start.py` проверяемая функция `init` стала корутиной: вызов в тесте оборачивается в `await`, а мок сессии заменяется на `MagicMock`, у которого `exec` — `AsyncMock`.

Декоратор `@pytest.mark.asyncio` не нужен: он подставляется автоматически благодаря `asyncio_mode = "auto"`.

- [ ] **Step 13: Поднять БД и прогнать весь набор тестов**

Run: `docker compose up -d db`
Expected: контейнер `db` в состоянии running.

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS по всем тестам, ни одного ERROR и ни одного предупреждения о нераспознанной корутине.

- [ ] **Step 14: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: `Success: no issues found` и отсутствие замечаний ruff.

- [ ] **Step 15: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app backend/tests
git commit -m "refactor: перевести бэкенд на async и починить сборку"
```

---

### Task 2: Шифрование секретов

**Files:**
- Create: `backend/app/core/crypto.py`
- Create: `backend/tests/core/__init__.py`
- Create: `backend/tests/core/test_crypto.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env`
- Modify: `compose.yml`, `compose.override.yml`

**Interfaces:**
- Consumes: `app.core.config.settings` из задачи 1.
- Produces:
  - `app.core.crypto.encrypt(plaintext: bytes) -> bytes`
  - `app.core.crypto.decrypt(payload: bytes) -> bytes`
  - `settings.CONNECTOR_SECRET_KEY: str` — urlsafe-base64 от ровно 32 байт

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/core/__init__.py` пустым файлом и `backend/tests/core/test_crypto.py`:

```python
import pytest
from cryptography.exceptions import InvalidTag

from app.core import crypto


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = b'{"password": "s3cret"}'

    restored = crypto.decrypt(crypto.encrypt(plaintext))

    assert restored == plaintext


def test_ciphertext_does_not_contain_plaintext() -> None:
    plaintext = b"very-secret-password"

    payload = crypto.encrypt(plaintext)

    assert plaintext not in payload


def test_same_plaintext_encrypts_to_different_payloads() -> None:
    plaintext = b"same input"

    first = crypto.encrypt(plaintext)
    second = crypto.encrypt(plaintext)

    assert first != second


def test_tampered_payload_is_rejected() -> None:
    payload = bytearray(crypto.encrypt(b"payload"))
    payload[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        crypto.decrypt(bytes(payload))
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/core/test_crypto.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.core.crypto'`.

- [ ] **Step 3: Добавить настройку CONNECTOR_SECRET_KEY**

В `backend/app/core/config.py` добавить импорт `base64` в начало файла, объявить поле рядом с `SECRET_KEY`:

```python
    CONNECTOR_SECRET_KEY: str
```

и добавить в класс `Settings` валидатор:

```python
    @field_validator("CONNECTOR_SECRET_KEY")
    @classmethod
    def _validate_connector_secret_key(cls, value: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(value)
        except Exception:
            raise ValueError(
                "CONNECTOR_SECRET_KEY must be urlsafe base64"
            ) from None
        if len(raw) != 32:
            raise ValueError(
                "CONNECTOR_SECRET_KEY must decode to exactly 32 bytes"
            )
        return value
```

- [ ] **Step 4: Сгенерировать ключ и прописать его в окружение**

Run: `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
Expected: строка из 44 символов, оканчивающаяся на `=`.

Добавить её в `.env` рядом с `SECRET_KEY`:

```
CONNECTOR_SECRET_KEY=<полученное значение>
```

В `compose.yml` в секции `environment` сервиса `backend` (и `prestart`, если у него есть собственный список переменных) добавить строку рядом с `SECRET_KEY`:

```yaml
      CONNECTOR_SECRET_KEY: ${CONNECTOR_SECRET_KEY?Variable not set}
```

- [ ] **Step 5: Реализовать модуль шифрования**

Создать `backend/app/core/crypto.py`:

```python
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE = 12


def _key() -> bytes:
    return base64.urlsafe_b64decode(settings.CONNECTOR_SECRET_KEY)


def encrypt(plaintext: bytes) -> bytes:
    """Зашифровать данные. Возвращает nonce, склеенный с шифротекстом."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(payload: bytes) -> bytes:
    """Расшифровать данные, полученные из encrypt().

    Бросает cryptography.exceptions.InvalidTag, если данные повреждены
    или зашифрованы другим ключом.
    """
    nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/core/test_crypto.py -v`
Expected: PASS, 4 теста.

- [ ] **Step 7: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/crypto.py backend/app/core/config.py backend/tests/core compose.yml
git commit -m "feat: шифрование учётных данных коннекторов через AES-GCM"
```

---

### Task 3: Контракт адаптера и реестр типов

**Files:**
- Create: `backend/app/adapters/__init__.py`
- Create: `backend/app/adapters/protocol.py`
- Create: `backend/app/adapters/registry.py`
- Create: `backend/tests/adapters/__init__.py`
- Create: `backend/tests/adapters/conftest.py`
- Create: `backend/tests/adapters/test_registry.py`

**Interfaces:**
- Consumes: ничего сверх стандартной библиотеки и pydantic.
- Produces:
  - `app.adapters.protocol.ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]`
  - `app.adapters.protocol.ConnectionCheckResult` с полями `ok: bool`, `message: str`, `latency_ms: int | None`, `error_kind: ErrorKind | None`
  - `app.adapters.protocol.DataAdapter` — Protocol с методом `async def check_connection(self) -> ConnectionCheckResult`
  - `app.adapters.registry.AdapterType` — frozen dataclass с полями `name`, `title`, `options_schema`, `factory`
  - `app.adapters.registry.register(name, title, options_schema)` — декоратор фабрики
  - `app.adapters.registry.get(name) -> AdapterType`, бросает `UnknownAdapterType`
  - `app.adapters.registry.all_types() -> list[AdapterType]`, отсортирован по `title`
  - `app.adapters.registry.secret_field_names(schema) -> set[str]`
  - `app.adapters.registry.UnknownAdapterType(Exception)`
  - фикстура `isolated_registry` в `tests/adapters/conftest.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/adapters/__init__.py` пустым файлом.

Создать `backend/tests/adapters/conftest.py` — фикстура, изолирующая реестр, чтобы регистрации из тестов не протекали в другие тесты:

```python
from collections.abc import Generator

import pytest

from app.adapters import registry


@pytest.fixture
def isolated_registry() -> Generator[None]:
    saved = dict(registry._registry)
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)
```

Создать `backend/tests/adapters/test_registry.py`:

```python
import pytest
from pydantic import BaseModel, SecretStr

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult


class FakeOptions(BaseModel):
    host: str
    port: int = 5432
    password: SecretStr


class FakeAdapter:
    def __init__(self, options: FakeOptions) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="fake", latency_ms=1)


def test_registered_type_is_retrievable(isolated_registry: None) -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    adapter_type = registry.get("fake")

    assert adapter_type.name == "fake"
    assert adapter_type.title == "Fake"
    assert adapter_type.options_schema is FakeOptions


def test_factory_builds_adapter(isolated_registry: None) -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    adapter = registry.get("fake").factory(
        FakeOptions(host="h", password=SecretStr("p"))
    )

    assert isinstance(adapter, FakeAdapter)


def test_unknown_type_raises(isolated_registry: None) -> None:
    with pytest.raises(registry.UnknownAdapterType):
        registry.get("nope")


def test_duplicate_registration_raises(isolated_registry: None) -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(name="fake", title="Other", options_schema=FakeOptions)(
            FakeAdapter
        )


def test_all_types_sorted_by_title(isolated_registry: None) -> None:
    registry._registry.clear()
    registry.register(name="b", title="Zeta", options_schema=FakeOptions)(FakeAdapter)
    registry.register(name="a", title="Alpha", options_schema=FakeOptions)(FakeAdapter)

    assert [t.title for t in registry.all_types()] == ["Alpha", "Zeta"]


def test_secret_field_names_finds_only_secretstr_fields() -> None:
    assert registry.secret_field_names(FakeOptions) == {"password"}
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/adapters/test_registry.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.adapters'`.

- [ ] **Step 3: Реализовать протокол**

Создать `backend/app/adapters/__init__.py` пустым файлом.

Создать `backend/app/adapters/protocol.py`:

```python
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class ConnectionCheckResult(BaseModel):
    """Итог проверки соединения.

    Драйверы никогда не выпускают наружу собственные исключения: их текст
    регулярно содержит строку подключения вместе с паролем.
    """

    ok: bool
    message: str
    latency_ms: int | None = None
    error_kind: ErrorKind | None = None


@runtime_checkable
class DataAdapter(Protocol):
    async def check_connection(self) -> ConnectionCheckResult: ...
```

- [ ] **Step 4: Реализовать реестр**

Создать `backend/app/adapters/registry.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, SecretStr

from app.adapters.protocol import DataAdapter


class UnknownAdapterType(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown adapter type: {name}")
        self.name = name


@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    options_schema: type[BaseModel]
    factory: Callable[[Any], DataAdapter]


_registry: dict[str, AdapterType] = {}

Factory = Callable[[Any], DataAdapter]


def register(
    *, name: str, title: str, options_schema: type[BaseModel]
) -> Callable[[Factory], Factory]:
    def decorator(factory: Factory) -> Factory:
        if name in _registry:
            raise ValueError(f"Adapter type already registered: {name}")
        _registry[name] = AdapterType(
            name=name, title=title, options_schema=options_schema, factory=factory
        )
        return factory

    return decorator


def get(name: str) -> AdapterType:
    try:
        return _registry[name]
    except KeyError:
        raise UnknownAdapterType(name) from None


def all_types() -> list[AdapterType]:
    return sorted(_registry.values(), key=lambda t: t.title)


def secret_field_names(schema: type[BaseModel]) -> set[str]:
    """Имена полей схемы, объявленных как SecretStr.

    Единственный источник истины о том, какие значения подлежат шифрованию.
    """
    return {
        name
        for name, field in schema.model_fields.items()
        if field.annotation is SecretStr
    }
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/adapters/test_registry.py -v`
Expected: PASS, 6 тестов.

- [ ] **Step 6: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 7: Commit**

```bash
git add backend/app/adapters backend/tests/adapters
git commit -m "feat: контракт адаптера и реестр типов источников"
```

---

### Task 4: Адаптер PostgreSQL

**Files:**
- Create: `backend/app/adapters/postgres/__init__.py`
- Create: `backend/app/adapters/postgres/options.py`
- Create: `backend/app/adapters/postgres/adapter.py`
- Create: `backend/tests/adapters/test_postgres.py`
- Modify: `backend/app/adapters/__init__.py`

**Interfaces:**
- Consumes: `registry.register`, `ConnectionCheckResult`, `ErrorKind` из задачи 3.
- Produces:
  - `app.adapters.postgres.options.PostgresOptions` с полями `host: str`, `port: int = 5432`, `database: str`, `user: str`, `password: SecretStr`
  - `app.adapters.postgres.adapter.PostgresAdapter`, зарегистрированный под именем `"postgres"` с заголовком `"PostgreSQL"`
  - `app.adapters.postgres.adapter.CHECK_TIMEOUT_SECONDS = 5.0`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/adapters/test_postgres.py`. Тесты работают против той же БД, что поднимается через `docker compose up -d db`, и берут её параметры из настроек приложения:

```python
from pydantic import SecretStr

from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.adapter import PostgresAdapter
from app.core.config import settings

WRONG_PASSWORD = "definitely-not-the-password"


def _working_options() -> PostgresOptions:
    url = settings.DATABASE_URL
    return PostgresOptions(
        host=url.host or "localhost",
        port=url.port or 5432,
        database=(url.path or "/app").lstrip("/"),
        user=url.username or "postgres",
        password=SecretStr(url.password or ""),
    )


async def test_check_connection_succeeds() -> None:
    result = await PostgresAdapter(_working_options()).check_connection()

    assert result.ok is True
    assert result.error_kind is None
    assert result.latency_ms is not None and result.latency_ms >= 0


async def test_wrong_password_is_classified_as_auth() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


async def test_unreachable_host_is_classified_as_network() -> None:
    options = _working_options().model_copy(update={"host": "127.0.0.1", "port": 1})

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "network"


async def test_error_message_never_leaks_the_password() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert WRONG_PASSWORD not in result.message


async def test_adapter_type_is_registered() -> None:
    from app.adapters import registry

    adapter_type = registry.get("postgres")

    assert adapter_type.title == "PostgreSQL"
    assert adapter_type.options_schema is PostgresOptions
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/adapters/test_postgres.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.adapters.postgres'`.

- [ ] **Step 3: Описать схему опций**

Создать `backend/app/adapters/postgres/__init__.py`:

```python
from app.adapters.postgres import adapter  # noqa: F401
```

Создать `backend/app/adapters/postgres/options.py`:

```python
from pydantic import BaseModel, Field, SecretStr


class PostgresOptions(BaseModel):
    host: str = Field(title="Host", min_length=1)
    port: int = Field(default=5432, title="Port", ge=1, le=65535)
    database: str = Field(title="Database", min_length=1)
    user: str = Field(title="User", min_length=1)
    password: SecretStr = Field(title="Password")
```

- [ ] **Step 4: Реализовать адаптер**

Создать `backend/app/adapters/postgres/adapter.py`:

```python
import asyncio
import time

import psycopg

from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import ConnectionCheckResult, ErrorKind
from app.adapters.registry import register

CHECK_TIMEOUT_SECONDS = 5.0

_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")


def _classify(exc: BaseException) -> tuple[ErrorKind, str]:
    """Свести исключение драйвера к безопасной паре (вид, сообщение).

    Текст исключения наружу не передаётся: psycopg включает в него строку
    подключения вместе с паролем.
    """
    if isinstance(exc, TimeoutError):
        return "timeout", "Connection timed out"
    if isinstance(exc, psycopg.OperationalError):
        text = str(exc).lower()
        if any(marker in text for marker in _AUTH_MARKERS):
            return "auth", "Authentication failed"
        return "network", "Could not reach the database server"
    return "unknown", "Connection failed"


class PostgresAdapter:
    def __init__(self, options: PostgresOptions) -> None:
        self._options = options

    def _conninfo(self) -> str:
        options = self._options
        return psycopg.conninfo.make_conninfo(
            host=options.host,
            port=options.port,
            dbname=options.database,
            user=options.user,
            password=options.password.get_secret_value(),
        )

    async def check_connection(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self._conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            error_kind, message = _classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=latency_ms
        )


@register(name="postgres", title="PostgreSQL", options_schema=PostgresOptions)
def _build(options: PostgresOptions) -> PostgresAdapter:
    return PostgresAdapter(options)
```

`asyncio.wait_for` при истечении таймаута бросает `TimeoutError` — с Python 3.11 это псевдоним `asyncio.TimeoutError`, поэтому проверка в `_classify` покрывает оба случая.

- [ ] **Step 5: Подключить драйвер к импорту пакета**

Заменить содержимое `backend/app/adapters/__init__.py`:

```python
# Импорт ради побочного эффекта: драйверы регистрируются в реестре при импорте.
from app.adapters import postgres  # noqa: F401
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `docker compose up -d db && cd backend && uv run pytest tests/adapters/ -v`
Expected: PASS, 11 тестов (6 из задачи 3 и 5 новых).

- [ ] **Step 7: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 8: Commit**

```bash
git add backend/app/adapters backend/tests/adapters
git commit -m "feat: адаптер PostgreSQL с классификацией и санитизацией ошибок"
```

---

### Task 5: Модель Connector и миграция

**Files:**
- Create: `backend/app/connectors/__init__.py`
- Create: `backend/app/connectors/models.py`
- Create: `backend/app/alembic/versions/<hash>_add_connector.py` (генерируется)
- Create: `backend/tests/connectors/__init__.py`
- Create: `backend/tests/connectors/test_models.py`
- Modify: `backend/app/alembic/env.py`

**Interfaces:**
- Consumes: `app.models.get_datetime_utc`, `app.models.User` из задачи 1.
- Produces:
  - `app.connectors.models.Connector` — таблица `connector`
  - `app.connectors.models.ConnectorCreate` с полями `name: str`, `adapter_type: str`, `options: dict[str, Any]`
  - `app.connectors.models.ConnectorUpdate` с полями `name: str | None`, `options: dict[str, Any] | None`
  - `app.connectors.models.ConnectorPublic` с полями `id`, `name`, `adapter_type`, `config`, `created_at`, `updated_at`
  - `app.connectors.models.ConnectorsPublic` с полями `data: list[ConnectorPublic]`, `count: int`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/connectors/__init__.py` пустым файлом и `backend/tests/connectors/test_models.py`:

```python
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector, ConnectorPublic
from app.models import User
from tests.utils.user import create_random_user


async def test_connector_is_persisted(db: AsyncSession) -> None:
    user = await create_random_user(db)
    connector = Connector(
        name="local pg",
        adapter_type="postgres",
        config={"host": "localhost", "port": 5432},
        secrets=b"encrypted",
        owner_id=user.id,
    )

    db.add(connector)
    await db.commit()
    await db.refresh(connector)

    assert connector.id is not None
    assert connector.created_at is not None
    assert connector.config["host"] == "localhost"


async def test_name_is_unique_per_owner(db: AsyncSession) -> None:
    user = await create_random_user(db)
    for _ in range(2):
        db.add(
            Connector(
                name="duplicate",
                adapter_type="postgres",
                config={},
                secrets=b"x",
                owner_id=user.id,
            )
        )

    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_same_name_allowed_for_different_owners(db: AsyncSession) -> None:
    first = await create_random_user(db)
    second = await create_random_user(db)
    for owner in (first, second):
        db.add(
            Connector(
                name="shared name",
                adapter_type="postgres",
                config={},
                secrets=b"x",
                owner_id=owner.id,
            )
        )

    await db.commit()

    result = await db.exec(select(Connector).where(Connector.name == "shared name"))
    assert len(result.all()) == 2


async def test_connectors_are_deleted_with_owner(db: AsyncSession) -> None:
    user = await create_random_user(db)
    db.add(
        Connector(
            name="to be orphaned",
            adapter_type="postgres",
            config={},
            secrets=b"x",
            owner_id=user.id,
        )
    )
    await db.commit()

    await db.delete(user)
    await db.commit()

    result = await db.exec(
        select(Connector).where(Connector.owner_id == user.id)
    )
    assert result.all() == []


def test_public_model_has_no_secrets_field() -> None:
    assert "secrets" not in ConnectorPublic.model_fields
```

Функция `create_random_user` уже существует в `backend/tests/utils/user.py:22` и к этому моменту переведена на async задачей 1, шаг 12. Её сигнатура должна быть `async def create_random_user(db: AsyncSession) -> User`.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/connectors/test_models.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.connectors'`.

- [ ] **Step 3: Описать модель и схемы API**

Создать `backend/app/connectors/__init__.py` пустым файлом.

Создать `backend/app/connectors/models.py`:

```python
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models import get_datetime_utc


class Connector(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_connector_owner_name"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=255)
    # Ключ реестра типов адаптеров, а не внешний ключ: реестр живёт в коде.
    adapter_type: str = Field(max_length=64)
    config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    secrets: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ConnectorCreate(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    adapter_type: str = Field(max_length=64)
    options: dict[str, Any]


class ConnectorUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    options: dict[str, Any] | None = None


class ConnectorPublic(SQLModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    config: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectorsPublic(SQLModel):
    data: list[ConnectorPublic]
    count: int
```

- [ ] **Step 4: Сделать модель видимой для Alembic**

В `backend/app/alembic/env.py` рядом со строкой `from app.models import SQLModel  # noqa` добавить:

```python
from app.connectors.models import Connector  # noqa
```

Без этого импорта таблица не попадёт в `SQLModel.metadata`, и автогенерация её не увидит.

- [ ] **Step 5: Сгенерировать миграцию**

Run: `docker compose up -d db && cd backend && uv run alembic revision --autogenerate -m "add connector"`
Expected: создан файл в `backend/app/alembic/versions/`.

Открыть созданный файл и проверить, что в `upgrade()` присутствуют: создание таблицы `connector`, столбцы `config` типа `JSONB` и `secrets` типа `LargeBinary`, внешний ключ на `user.id` с `ondelete="CASCADE"`, ограничение `uq_connector_owner_name`. Лишних операций (удаление или изменение чужих таблиц) быть не должно — если они есть, удалить их вручную.

- [ ] **Step 6: Применить миграцию**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade ... -> <hash>, add connector`.

- [ ] **Step 7: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/connectors/test_models.py -v`
Expected: PASS, 5 тестов.

- [ ] **Step 8: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add backend/app/connectors backend/app/alembic backend/tests/connectors backend/tests/utils
git commit -m "feat: модель коннектора и миграция"
```

---

### Task 6: Раскладка опций на конфигурацию и секреты

**Files:**
- Create: `backend/app/connectors/service.py`
- Create: `backend/tests/connectors/test_service.py`

**Interfaces:**
- Consumes: `registry.get`, `registry.secret_field_names`, `registry.AdapterType` из задачи 3; `crypto.encrypt`, `crypto.decrypt` из задачи 2.
- Produces:
  - `app.connectors.service.split_options(adapter_type: AdapterType, options: dict[str, Any]) -> tuple[dict[str, Any], bytes]`
  - `app.connectors.service.merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]`
  - `app.connectors.service.fill_missing_secrets(adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]`
  - `app.connectors.service.build_adapter(adapter_type: AdapterType, options: dict[str, Any]) -> DataAdapter`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/connectors/test_service.py`:

```python
import json

import pytest
from pydantic import ValidationError

from app.adapters import registry
from app.adapters.postgres.adapter import PostgresAdapter
from app.connectors import service
from app.core import crypto

OPTIONS = {
    "host": "db.example.com",
    "port": 6432,
    "database": "analytics",
    "user": "reader",
    "password": "s3cret",
}


def _postgres_type() -> registry.AdapterType:
    return registry.get("postgres")


def test_secret_fields_are_kept_out_of_config() -> None:
    config, _ = service.split_options(_postgres_type(), OPTIONS)

    assert "password" not in config
    assert config == {
        "host": "db.example.com",
        "port": 6432,
        "database": "analytics",
        "user": "reader",
    }


def test_config_is_json_serialisable() -> None:
    config, _ = service.split_options(_postgres_type(), OPTIONS)

    assert json.loads(json.dumps(config)) == config


def test_secrets_blob_does_not_contain_the_password() -> None:
    _, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert b"s3cret" not in secrets_blob


def test_merge_restores_original_options() -> None:
    config, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert service.merge_options(config, secrets_blob) == OPTIONS


def test_invalid_options_are_rejected() -> None:
    with pytest.raises(ValidationError):
        service.split_options(_postgres_type(), {"host": "only-host"})


def test_fill_missing_secrets_takes_stored_value() -> None:
    adapter_type = _postgres_type()
    _, secrets_blob = service.split_options(adapter_type, OPTIONS)
    incoming = {k: v for k, v in OPTIONS.items() if k != "password"}

    filled = service.fill_missing_secrets(adapter_type, incoming, secrets_blob)

    assert filled["password"] == "s3cret"


def test_fill_missing_secrets_prefers_supplied_value() -> None:
    adapter_type = _postgres_type()
    _, secrets_blob = service.split_options(adapter_type, OPTIONS)
    incoming = {**OPTIONS, "password": "new-password"}

    filled = service.fill_missing_secrets(adapter_type, incoming, secrets_blob)

    assert filled["password"] == "new-password"


def test_build_adapter_returns_driver_instance() -> None:
    adapter = service.build_adapter(_postgres_type(), OPTIONS)

    assert isinstance(adapter, PostgresAdapter)


def test_encrypted_blob_is_readable_only_through_crypto() -> None:
    _, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert json.loads(crypto.decrypt(secrets_blob)) == {"password": "s3cret"}
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/connectors/test_service.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.connectors.service'`.

- [ ] **Step 3: Реализовать сервис**

Создать `backend/app/connectors/service.py`:

```python
import json
from typing import Any

from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterType, secret_field_names
from app.core import crypto


def split_options(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Разделить опции на несекретную конфигурацию и зашифрованные секреты.

    Разделение выполняется по объявлению схемы (какие поля SecretStr), а не по
    отдельному списку: забыть пометить поле невозможно.
    """
    model = adapter_type.options_schema.model_validate(options)
    secret_names = secret_field_names(adapter_type.options_schema)
    dumped = model.model_dump(mode="json")

    config = {name: value for name, value in dumped.items() if name not in secret_names}
    secrets = {
        name: getattr(model, name).get_secret_value()
        for name in secret_names
        if getattr(model, name) is not None
    }
    return config, crypto.encrypt(json.dumps(secrets).encode())


def merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]:
    """Собрать полный набор опций обратно из конфигурации и секретов."""
    secrets = json.loads(crypto.decrypt(secrets_blob))
    return {**config, **secrets}


def fill_missing_secrets(
    adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes
) -> dict[str, Any]:
    """Подставить сохранённые секреты вместо непереданных.

    Нужно и для PATCH, и для проверки соединения при редактировании:
    пользователь правит порт, не вводя пароль заново.
    """
    stored = json.loads(crypto.decrypt(secrets_blob))
    filled = dict(options)
    for name in secret_field_names(adapter_type.options_schema):
        if not filled.get(name) and name in stored:
            filled[name] = stored[name]
    return filled


def build_adapter(adapter_type: AdapterType, options: dict[str, Any]) -> DataAdapter:
    model = adapter_type.options_schema.model_validate(options)
    return adapter_type.factory(model)
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/connectors/test_service.py -v`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors/service.py backend/tests/connectors/test_service.py
git commit -m "feat: раскладка опций коннектора на конфигурацию и шифрованные секреты"
```

---

### Task 7: CRUD-ручки коннекторов

**Files:**
- Create: `backend/app/connectors/crud.py`
- Create: `backend/app/connectors/routes.py`
- Create: `backend/tests/connectors/test_routes.py`
- Modify: `backend/app/api/main.py`

**Interfaces:**
- Consumes: `SessionDep`, `CurrentUser` из задачи 1; модели из задачи 5; `split_options`, `fill_missing_secrets` из задачи 6; `registry.get`, `UnknownAdapterType` из задачи 3.
- Produces:
  - `app.connectors.crud.create(session, *, name: str, adapter_type: str, config: dict[str, Any], secrets: bytes, owner_id: uuid.UUID) -> Connector`
  - `app.connectors.crud.get(session, *, connector_id: uuid.UUID, owner: User) -> Connector | None`
  - `app.connectors.crud.list_for(session, *, owner: User, skip: int, limit: int) -> tuple[list[Connector], int]`
  - `app.connectors.crud.save(session, *, connector: Connector) -> Connector`
  - `app.connectors.crud.delete(session, *, connector: Connector) -> None`
  - роутер `app.connectors.routes.router` с префиксом `/connectors`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/connectors/test_routes.py`:

```python
import uuid

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.config import settings

PASSWORD = "top-secret-value"
BASE = f"{settings.API_V1_STR}/connectors"


def _payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "adapter_type": "postgres",
        "options": {
            "host": "localhost",
            "port": 5432,
            "database": "app",
            "user": "postgres",
            "password": PASSWORD,
        },
    }


async def test_create_returns_connector_without_secrets(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        BASE, headers=normal_user_token_headers, json=_payload("created")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "created"
    assert body["adapter_type"] == "postgres"
    assert body["config"]["host"] == "localhost"
    assert "secrets" not in body
    assert PASSWORD not in response.text


async def test_stored_secrets_are_encrypted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    response = await client.post(
        BASE, headers=normal_user_token_headers, json=_payload("encrypted")
    )
    connector_id = uuid.UUID(response.json()["id"])

    stored = await db.get(Connector, connector_id)

    assert stored is not None
    assert PASSWORD.encode() not in stored.secrets
    assert "password" not in stored.config


async def test_unknown_adapter_type_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = _payload("bad type") | {"adapter_type": "nope"}

    response = await client.post(BASE, headers=normal_user_token_headers, json=payload)

    assert response.status_code == 422


async def test_invalid_options_are_rejected_with_field_path(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = _payload("bad options")
    payload["options"] = {"host": "localhost"}

    response = await client.post(BASE, headers=normal_user_token_headers, json=payload)

    assert response.status_code == 422
    locations = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert any("database" in location for location in locations)


async def test_list_returns_only_own_connectors(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    await client.post(
        BASE, headers=superuser_token_headers, json=_payload("superuser only")
    )

    response = await client.get(BASE, headers=normal_user_token_headers)

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]]
    assert "superuser only" not in names


async def test_foreign_connector_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    created = await client.post(
        BASE, headers=superuser_token_headers, json=_payload("foreign")
    )
    connector_id = created.json()["id"]

    response = await client.get(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_patch_without_options_preserves_secrets(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        BASE, headers=normal_user_token_headers, json=_payload("renamed")
    )
    connector_id = uuid.UUID(created.json()["id"])
    before = await db.get(Connector, connector_id)
    assert before is not None
    secrets_before = before.secrets

    response = await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={"name": "renamed twice"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "renamed twice"
    await db.refresh(before)
    assert before.secrets == secrets_before


async def test_patch_with_partial_options_keeps_stored_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        BASE, headers=normal_user_token_headers, json=_payload("port change")
    )
    connector_id = uuid.UUID(created.json()["id"])

    response = await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={
            "options": {
                "host": "localhost",
                "port": 6543,
                "database": "app",
                "user": "postgres",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["port"] == 6543
    stored = await db.get(Connector, connector_id)
    assert stored is not None
    assert PASSWORD.encode() not in stored.secrets


async def test_delete_removes_connector(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        BASE, headers=normal_user_token_headers, json=_payload("deleted")
    )
    connector_id = uuid.UUID(created.json()["id"])

    response = await client.delete(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    result = await db.exec(select(Connector).where(Connector.id == connector_id))
    assert result.first() is None


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.get(BASE)

    assert response.status_code == 401
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/connectors/test_routes.py -v`
Expected: FAIL — все запросы возвращают 404, поскольку роутер не подключён.

- [ ] **Step 3: Реализовать доступ к БД**

Создать `backend/app/connectors/crud.py`:

```python
import uuid
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.models import User


async def create(
    session: AsyncSession,
    *,
    name: str,
    adapter_type: str,
    config: dict[str, Any],
    secrets: bytes,
    owner_id: uuid.UUID,
) -> Connector:
    connector = Connector(
        name=name,
        adapter_type=adapter_type,
        config=config,
        secrets=secrets,
        owner_id=owner_id,
    )
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def get(
    session: AsyncSession, *, connector_id: uuid.UUID, owner: User
) -> Connector | None:
    connector = await session.get(Connector, connector_id)
    if connector is None:
        return None
    if connector.owner_id != owner.id and not owner.is_superuser:
        # Чужой коннектор неотличим от несуществующего: иначе перебором
        # идентификаторов выясняется, какие подключения есть у других.
        return None
    return connector


async def list_for(
    session: AsyncSession, *, owner: User, skip: int = 0, limit: int = 100
) -> tuple[list[Connector], int]:
    count_statement = select(func.count()).select_from(Connector)
    statement = select(Connector).order_by(col(Connector.created_at).desc())
    if not owner.is_superuser:
        count_statement = count_statement.where(Connector.owner_id == owner.id)
        statement = statement.where(Connector.owner_id == owner.id)

    count = (await session.exec(count_statement)).one()
    connectors = (await session.exec(statement.offset(skip).limit(limit))).all()
    return list(connectors), count


async def save(session: AsyncSession, *, connector: Connector) -> Connector:
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def delete(session: AsyncSession, *, connector: Connector) -> None:
    await session.delete(connector)
    await session.commit()
```

- [ ] **Step 4: Реализовать ручки**

Создать `backend/app/connectors/routes.py`:

```python
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.adapters.registry import AdapterType, UnknownAdapterType
from app.adapters.registry import get as get_adapter_type
from app.api.deps import CurrentUser, SessionDep
from app.connectors import crud, service
from app.connectors.models import (
    Connector,
    ConnectorCreate,
    ConnectorPublic,
    ConnectorsPublic,
    ConnectorUpdate,
)
from app.models import Message, User, get_datetime_utc
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _resolve_type(adapter_type: str) -> AdapterType:
    try:
        return get_adapter_type(adapter_type)
    except UnknownAdapterType:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "adapter_type"],
                    "msg": f"Unknown adapter type: {adapter_type}",
                    "type": "value_error",
                }
            ],
        )


def _split_or_422(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    try:
        return service.split_options(adapter_type, options)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "options", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        )


async def _get_or_404(
    session: AsyncSession, connector_id: uuid.UUID, current_user: User
) -> Connector:
    connector = await crud.get(session, connector_id=connector_id, owner=current_user)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


@router.post("/", response_model=ConnectorPublic)
async def create_connector(
    session: SessionDep, current_user: CurrentUser, connector_in: ConnectorCreate
) -> Any:
    adapter_type = _resolve_type(connector_in.adapter_type)
    config, secrets = _split_or_422(adapter_type, connector_in.options)
    return await crud.create(
        session,
        name=connector_in.name,
        adapter_type=adapter_type.name,
        config=config,
        secrets=secrets,
        owner_id=current_user.id,
    )


@router.get("/", response_model=ConnectorsPublic)
async def read_connectors(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    connectors, count = await crud.list_for(
        session, owner=current_user, skip=skip, limit=limit
    )
    return ConnectorsPublic(data=connectors, count=count)


@router.get("/{connector_id}", response_model=ConnectorPublic)
async def read_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    return await _get_or_404(session, connector_id, current_user)


@router.patch("/{connector_id}", response_model=ConnectorPublic)
async def update_connector(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    connector_in: ConnectorUpdate,
) -> Any:
    connector = await _get_or_404(session, connector_id, current_user)

    if connector_in.name is not None:
        connector.name = connector_in.name

    if connector_in.options is not None:
        adapter_type = _resolve_type(connector.adapter_type)
        options = service.fill_missing_secrets(
            adapter_type, connector_in.options, connector.secrets
        )
        connector.config, connector.secrets = _split_or_422(adapter_type, options)

    connector.updated_at = get_datetime_utc()
    return await crud.save(session, connector=connector)


@router.delete("/{connector_id}")
async def delete_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Message:
    connector = await _get_or_404(session, connector_id, current_user)
    await crud.delete(session, connector=connector)
    return Message(message="Connector deleted successfully")
```

- [ ] **Step 5: Подключить роутер**

В `backend/app/api/main.py` добавить импорт и подключение:

```python
from app.connectors.routes import router as connectors_router
```

и рядом с остальными вызовами `include_router`:

```python
api_router.include_router(connectors_router)
```

Импорт `app.connectors.routes` тянет за собой `app.adapters`, поэтому драйверы регистрируются при старте приложения.

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/connectors/test_routes.py -v`
Expected: PASS, 11 тестов.

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS целиком.

- [ ] **Step 8: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add backend/app/connectors backend/app/api/main.py backend/tests/connectors
git commit -m "feat: CRUD-ручки коннекторов с изоляцией по владельцу"
```

---

### Task 8: Список типов адаптеров и проверка соединения

**Files:**
- Create: `backend/app/adapters/routes.py`
- Create: `backend/tests/adapters/test_routes.py`
- Create: `backend/tests/connectors/test_check.py`
- Modify: `backend/app/connectors/routes.py`
- Modify: `backend/app/api/main.py`

**Interfaces:**
- Consumes: всё из задач 3, 4, 6, 7.
- Produces:
  - `GET /api/v1/adapter-types/` → `list[AdapterTypeInfo]`, где `AdapterTypeInfo` имеет поля `name: str`, `title: str`, `options_schema: dict[str, Any]`
  - `POST /api/v1/connectors/{connector_id}/check` → `ConnectionCheckResult`
  - `POST /api/v1/connectors/check-draft` → `ConnectionCheckResult`, тело `ConnectionCheckRequest` с полями `adapter_type: str`, `options: dict[str, Any]`, `connector_id: uuid.UUID | None`

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/adapters/test_routes.py`:

```python
from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/adapter-types"


async def test_lists_postgres_with_json_schema(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert response.status_code == 200
    types = {item["name"]: item for item in response.json()}
    assert types["postgres"]["title"] == "PostgreSQL"
    properties = types["postgres"]["options_schema"]["properties"]
    assert properties["host"]["title"] == "Host"
    assert properties["port"]["default"] == 5432


async def test_secret_fields_are_marked_as_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    postgres = next(item for item in response.json() if item["name"] == "postgres")
    assert postgres["options_schema"]["properties"]["password"]["format"] == "password"


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/")

    assert response.status_code == 401
```

Создать `backend/tests/connectors/test_check.py`:

```python
import uuid

from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/connectors"
WRONG_PASSWORD = "definitely-not-the-password"


def _working_options() -> dict[str, object]:
    url = settings.DATABASE_URL
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "database": (url.path or "/app").lstrip("/"),
        "user": url.username or "postgres",
        "password": url.password or "",
    }


async def test_check_draft_succeeds_with_valid_options(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": _working_options()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["latency_ms"] is not None


async def test_check_draft_reports_auth_failure_without_leaking_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    options = _working_options() | {"password": WRONG_PASSWORD}

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": options},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_kind"] == "auth"
    assert WRONG_PASSWORD not in response.text


async def test_check_draft_uses_stored_secret_when_password_omitted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        BASE,
        headers=normal_user_token_headers,
        json={
            "name": "draft check",
            "adapter_type": "postgres",
            "options": _working_options(),
        },
    )
    connector_id = created.json()["id"]
    options_without_password = {
        key: value for key, value in _working_options().items() if key != "password"
    }

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "options": options_without_password,
            "connector_id": connector_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_check_draft_rejects_foreign_connector_id(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    created = await client.post(
        BASE,
        headers=superuser_token_headers,
        json={
            "name": "foreign for check",
            "adapter_type": "postgres",
            "options": _working_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "options": {},
            "connector_id": connector_id,
        },
    )

    assert response.status_code == 404


async def test_check_saved_connector_succeeds(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        BASE,
        headers=normal_user_token_headers,
        json={
            "name": "saved check",
            "adapter_type": "postgres",
            "options": _working_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/check", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_check_unknown_connector_returns_404(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/check", headers=normal_user_token_headers
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd backend && uv run pytest tests/adapters/test_routes.py tests/connectors/test_check.py -v`
Expected: FAIL — ручки возвращают 404.

- [ ] **Step 3: Реализовать список типов адаптеров**

Создать `backend/app/adapters/routes.py`:

```python
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from fastapi import Depends

from app.adapters import registry
from app.api.deps import get_current_user

# Аутентификация объявлена на уровне роутера: сам обработчик пользователя не
# использует, а неиспользуемый параметр запрещён правилом ruff ARG001.
router = APIRouter(
    prefix="/adapter-types",
    tags=["adapter-types"],
    dependencies=[Depends(get_current_user)],
)


class AdapterTypeInfo(BaseModel):
    name: str
    title: str
    options_schema: dict[str, Any]


@router.get("/", response_model=list[AdapterTypeInfo])
async def read_adapter_types() -> Any:
    return [
        AdapterTypeInfo(
            name=adapter_type.name,
            title=adapter_type.title,
            options_schema=adapter_type.options_schema.model_json_schema(),
        )
        for adapter_type in registry.all_types()
    ]
```

- [ ] **Step 4: Добавить ручки проверки соединения**

В блоке импортов `backend/app/connectors/routes.py` добавить строку

```python
from app.adapters.protocol import ConnectionCheckResult
```

и дополнить существующий импорт pydantic до

```python
from pydantic import BaseModel, ValidationError
```

Затем добавить в конец файла:

```python
class ConnectionCheckRequest(BaseModel):
    adapter_type: str
    options: dict[str, Any]
    connector_id: uuid.UUID | None = None


@router.post("/check-draft", response_model=ConnectionCheckResult)
async def check_draft(
    session: SessionDep, current_user: CurrentUser, body: ConnectionCheckRequest
) -> Any:
    """Проверить соединение по данным формы, ничего не сохраняя.

    Если передан connector_id, недостающие секретные поля берутся из
    сохранённого коннектора: пользователь правит порт, не вводя пароль заново.
    """
    adapter_type = _resolve_type(body.adapter_type)
    options = body.options
    if body.connector_id is not None:
        connector = await _get_or_404(session, body.connector_id, current_user)
        options = service.fill_missing_secrets(
            adapter_type, options, connector.secrets
        )

    try:
        adapter = service.build_adapter(adapter_type, options)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "options", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        )
    return await adapter.check_connection()


@router.post("/{connector_id}/check", response_model=ConnectionCheckResult)
async def check_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    connector = await _get_or_404(session, connector_id, current_user)
    adapter_type = _resolve_type(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    adapter = service.build_adapter(adapter_type, options)
    return await adapter.check_connection()
```

- [ ] **Step 5: Подключить роутер типов адаптеров**

В `backend/app/api/main.py` добавить:

```python
from app.adapters.routes import router as adapter_types_router
```

и рядом с остальными:

```python
api_router.include_router(adapter_types_router)
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `cd backend && uv run pytest tests/adapters/test_routes.py tests/connectors/test_check.py -v`
Expected: PASS, 9 тестов.

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS целиком.

- [ ] **Step 8: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add backend/app/adapters backend/app/connectors backend/app/api/main.py backend/tests
git commit -m "feat: список типов адаптеров и проверка соединения"
```

---

### Task 9: Удалить учебную сущность Item

Выполняется последней: до этого момента `Item` служит работающим образцом под рукой.

**Files:**
- Delete: `backend/app/api/routes/items.py`
- Delete: `backend/tests/api/routes/test_items.py`
- Delete: `backend/tests/utils/item.py`
- Create: `backend/app/alembic/versions/<hash>_drop_item.py` (генерируется)
- Modify: `backend/app/models.py`, `backend/app/crud.py`, `backend/app/api/main.py`, `backend/app/api/routes/users.py`, `backend/tests/conftest.py`

**Interfaces:**
- Consumes: всё из задач 1–8.
- Produces: ничего нового; удаляет `Item`, `ItemBase`, `ItemCreate`, `ItemUpdate`, `ItemPublic`, `ItemsPublic`, `crud.create_item`.

- [ ] **Step 1: Убрать роутер items**

В `backend/app/api/main.py` удалить `items` из импорта `from app.api.routes import ...` и строку `api_router.include_router(items.router)`.

- [ ] **Step 2: Удалить файлы**

```bash
git rm backend/app/api/routes/items.py backend/tests/api/routes/test_items.py backend/tests/utils/item.py
```

- [ ] **Step 3: Убрать модели Item**

В `backend/app/models.py` удалить классы `ItemBase`, `ItemCreate`, `ItemUpdate`, `Item`, `ItemPublic`, `ItemsPublic`, а также поле `items` из класса `User`:

```python
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)
```

Если `Relationship` больше нигде не используется, удалить его из импорта `sqlmodel`.

- [ ] **Step 4: Убрать crud.create_item**

В `backend/app/crud.py` удалить функцию `create_item` и упоминания `Item`, `ItemCreate` в импорте из `app.models`.

- [ ] **Step 5: Поправить удаление пользователя**

В `backend/app/api/routes/users.py:228` удалить строку, вручную удаляющую связанные `Item`:

```python
    statement = delete(Item).where(col(Item.owner_id) == user_id)
```

вместе со следующей за ней строкой выполнения этого запроса, а также убрать `Item` из импорта в строке 16. Если после этого `delete` и `col` больше нигде в файле не используются, удалить и их из импорта. Каскад на уровне БД остаётся единственным механизмом — `Connector` уже полагается на него.

- [ ] **Step 6: Поправить conftest**

В `backend/tests/conftest.py` удалить импорт `Item` и строку `await session.execute(delete(Item))`. Добавить очистку коннекторов перед удалением пользователей:

```python
        await session.execute(delete(Connector))
        await session.execute(delete(User))
```

с импортом `from app.connectors.models import Connector`.

- [ ] **Step 7: Сгенерировать и применить миграцию**

Run: `cd backend && uv run alembic revision --autogenerate -m "drop item"`
Expected: создан файл миграции, в `upgrade()` присутствует `op.drop_table("item")`.

Run: `cd backend && uv run alembic upgrade head`
Expected: миграция применена.

- [ ] **Step 8: Прогнать весь набор тестов**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS целиком, тестов про `Item` не осталось.

- [ ] **Step 9: Проверить типы и стиль**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: без ошибок.

- [ ] **Step 10: Commit**

```bash
git add -A backend
git commit -m "chore: удалить учебную сущность Item"
```

---

## Итог

После задачи 9 бэкенд предоставляет:

- `GET /api/v1/adapter-types/` — типы источников с JSON Schema опций;
- полный CRUD коннекторов с изоляцией по владельцу;
- `POST /api/v1/connectors/{id}/check` и `POST /api/v1/connectors/check-draft`;
- шифрование учётных данных, не покидающих сервер.

Фронтенд на Vue описывается отдельным планом: `2026-08-15-connector-registry-frontend.md`.

## Известное ограничение

`check-draft` по своей природе открывает TCP-соединение на присланный клиентом адрес, что даёт авторизованному пользователю возможность картировать внутреннюю сеть по времени ответа и виду ошибки. В плане реализованы смягчающие меры — жёсткий таймаут и единообразные сообщения об ошибках. Ограничение хостов списком разрешённых адресов вынесено отдельной задачей в бэклог, точка расширения — функция `_classify` и построение строки подключения в `PostgresAdapter._conninfo`.
