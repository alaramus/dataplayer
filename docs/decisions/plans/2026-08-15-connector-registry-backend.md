# Implementation plan: connector registry, backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** an API that lets a user create a PostgreSQL connector, store its credentials encrypted and check the connection.

**Architecture:** Source types are described by a registry in code: the driver class and the Pydantic options schema sit next to each other. The database holds only `Connector`, where non-secret fields are stored in jsonb and secret ones in a separate encrypted field; the split is done automatically by the `SecretStr` type in the schema. The adapter contract is a `typing.Protocol` with a single method `check_connection()`, which never lets a driver exception escape.

**Tech Stack:** Python 3.14, FastAPI, SQLModel on top of SQLAlchemy 2 in async mode, psycopg 3 (async), Alembic, PostgreSQL, pytest + pytest-asyncio, cryptography (AES-GCM), uv.

Spec: [2026-08-15-connector-registry-design.md](../2026-08-15-connector-registry-design.md)

## Global Constraints

- Python 3.14; dependencies are installed with `uv`, commands are run with `uv run`.
- `uv run mypy app` (strict mode, set in `pyproject.toml`) and `uv run ruff check app tests` pass without errors after every task.
- All endpoints live under the `/api/v1` prefix (the value of `settings.API_V1_STR`).
- Secrets never appear in API responses, error messages or logs.
- The connection check timeout is exactly 5 seconds.
- The encryption key is the `CONNECTOR_SECRET_KEY` variable, separate from `SECRET_KEY`.
- New code is placed in modules (`app/adapters/`, `app/connectors/`). The flat `app/models.py`, `app/crud.py` and `app/api/routes/` are only converted to async in this plan, not moved (decision R5 of the spec).
- The database must be up before tests run: `docker compose up -d db`.
- **On Windows** psycopg 3 in async mode is incompatible with `ProactorEventLoop`, which Python picks by default, and fails with `InterfaceError`. The loop is created through `app.core.db.loop_factory` — it is wired into the startup scripts and into pytest-asyncio (the `_asyncio_loop_factory` fixture in `tests/conftest.py`). Event loop policies do not work for this: they are deprecated in Python 3.14. In the Linux container the factory returns an ordinary loop.
- Any blocking call in an async endpoint stalls the whole event loop. `send_email` talks SMTP synchronously, so it is called through `starlette.concurrency.run_in_threadpool`. The same rule applies to any new blocking code.

---

### Task 1: Get the backend working and convert it to async

The backend currently fails to import because of a syntax error, and the installed environment lags behind `pyproject.toml`. This task fixes that and converts the whole backend to async database access. It is done when the existing test suite passes in full.

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
- Consumes: nothing (first task).
- Produces:
  - `app.core.db.engine: AsyncEngine`
  - `app.core.db.async_session_maker: async_sessionmaker[AsyncSession]`
  - `app.core.db.init_db(session: AsyncSession) -> None`
  - `app.api.deps.SessionDep = Annotated[AsyncSession, Depends(get_db)]`
  - `app.api.deps.CurrentUser = Annotated[User, Depends(get_current_user)]`
  - every function in `app.crud` becomes `async def` with the same names and parameters
  - the `client` fixture in tests is `httpx.AsyncClient`, not `TestClient`

- [ ] **Step 1: Fix the syntax error in deps.py**

In `backend/app/api/deps.py:36` replace the line

```python
    except InvalidTokenError, ValidationError:
```

with

```python
    except (InvalidTokenError, ValidationError):
```

- [ ] **Step 2: Make sure the file compiles**

Run: `cd backend && python -m py_compile app/api/deps.py && echo OK`
Expected: `OK` with no traceback.

- [ ] **Step 3: Remove frontend serving from main.py**

`app.frontend()` raises `RuntimeError` if the directory does not exist, and `backend/app/frontend` appears only after the first frontend build — so the application fails to import, including in tests. The frontend is moving to Vue and runs on its own port in development, so serving comes back later, in task 8 of the frontend plan, with a check that the directory exists. Remove line 12 from `backend/app/main.py`

```python
FRONTEND_DIR = Path(__file__).parent / "frontend"
```

the last line of the file

```python
app.frontend("/", directory=FRONTEND_DIR)
```

and the import on line 1 that is no longer needed

```python
from pathlib import Path
```

- [ ] **Step 4: Add dependencies**

In `backend/pyproject.toml` add to the `dependencies` list:

```toml
    "cryptography>=44.0.0,<47.0.0",
```

In `[dependency-groups]` add to the `dev` list:

```toml
    "pytest-asyncio>=1.0.0,<2.0.0",
```

At the end of the file add the pytest settings (the file currently has no `[tool.pytest.ini_options]` section):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
```

- [ ] **Step 5: Sync the environment**

Run: `cd backend && uv sync`
Expected: `cryptography` and `pytest-asyncio` are installed.

All commands are run through `uv run`: a bare `python` in this repository picks up a different environment, with different package versions.

- [ ] **Step 6: Switch core/db.py to an async engine**

Replace the entire contents of `backend/app/core/db.py`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

engine = create_async_engine(str(settings.DATABASE_URL))

# expire_on_commit=False is required: otherwise accessing an object's field after
# commit() triggers a lazy load, which fails in async mode.
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

- [ ] **Step 7: Switch deps.py to AsyncSession**

Replace the entire contents of `backend/app/api/deps.py`:

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

- [ ] **Step 8: Convert crud.py to async**

Replace the entire contents of `backend/app/crud.py`:

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

- [ ] **Step 9: Convert the endpoints to async**

In `backend/app/api/routes/login.py`, `users.py`, `items.py`, `utils.py`, `private.py` apply a mechanical transformation. The rules applied to every handler function:

1. `def handler(...)` → `async def handler(...)`.
2. Every call to a function from `app.crud` gets `await`: `crud.create_user(...)` → `await crud.create_user(...)`.
3. `session.exec(statement)` → `result = await session.exec(statement)`, then `result.all()` / `result.one()` / `result.first()` instead of `session.exec(statement).all()` and so on.
4. `session.get(Model, id)` → `await session.get(Model, id)`.
5. `session.commit()` → `await session.commit()`; `session.refresh(obj)` → `await session.refresh(obj)`; `session.delete(obj)` → `await session.delete(obj)`.
6. `session.add(obj)` stays without `await` — it is a synchronous operation.

Example of the transformation for `read_items` in `items.py`:

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

The `get_current_active_superuser` function in `deps.py` stays synchronous — it does not touch the database, and FastAPI handles a synchronous dependency correctly.

- [ ] **Step 10: Convert the startup scripts to async**

In `backend/app/backend_pre_start.py` and `backend/app/tests_pre_start.py` the `init` function opens a session and runs `session.exec(select(1))`. Make the body async and run it through `asyncio.run`. For `backend_pre_start.py`:

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

Remove the unused `Engine` import. Apply the same transformation to `tests_pre_start.py`, keeping its own message texts.

In `backend/app/initial_data.py` replace the body with:

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

- [ ] **Step 11: Switch conftest.py to async fixtures**

Replace the entire contents of `backend/tests/conftest.py`:

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

The scope of the `client`, `superuser_token_headers` and `normal_user_token_headers` fixtures changes from `module` to `session` to match the event loop scope set in `asyncio_default_fixture_loop_scope`.

- [ ] **Step 12: Convert test utilities and tests to async**

In `backend/tests/utils/user.py`, `backend/tests/utils/item.py`, `backend/tests/utils/utils.py` and in every file in `backend/tests/api/routes/*.py`, `backend/tests/crud/test_user.py`, `backend/tests/scripts/*.py` apply the transformation:

1. Every test function and every helper that touches the database or the client becomes `async def`.
2. `client.get(...)`, `client.post(...)`, `client.patch(...)`, `client.delete(...)` get `await`.
3. Calls to `crud.*` get `await`.
4. `db.exec(...)`, `db.get(...)`, `db.commit()`, `db.refresh(...)`, `db.delete(...)` get `await`.
5. Type annotations `Session` → `AsyncSession` with the import `from sqlmodel.ext.asyncio.session import AsyncSession`.
6. Type annotations `TestClient` → `AsyncClient` with the import `from httpx import AsyncClient`.
7. In `backend/tests/scripts/test_backend_pre_start.py` and `test_test_pre_start.py` the `init` function under test is now a coroutine: the call in the test is wrapped in `await`, and the session mock is replaced with a `MagicMock` whose `exec` is an `AsyncMock`.

The `@pytest.mark.asyncio` decorator is not needed: it is applied automatically thanks to `asyncio_mode = "auto"`.

- [ ] **Step 13: Start the database and run the whole test suite**

Run: `docker compose up -d db`
Expected: the `db` container is running.

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS on every test, no ERROR and no warning about an unawaited coroutine.

- [ ] **Step 14: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: `Success: no issues found` and no ruff findings.

- [ ] **Step 15: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app backend/tests
git commit -m "refactor: convert the backend to async and fix the build"
```

---

### Task 2: Secret encryption

**Files:**
- Create: `backend/app/core/crypto.py`
- Create: `backend/tests/core/__init__.py`
- Create: `backend/tests/core/test_crypto.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env`
- Modify: `compose.yml`, `compose.override.yml`

**Interfaces:**
- Consumes: `app.core.config.settings` from task 1.
- Produces:
  - `app.core.crypto.encrypt(plaintext: bytes) -> bytes`
  - `app.core.crypto.decrypt(payload: bytes) -> bytes`
  - `settings.CONNECTOR_SECRET_KEY: str` — urlsafe base64 of exactly 32 bytes

- [ ] **Step 1: Write failing tests**

Create `backend/tests/core/__init__.py` as an empty file and `backend/tests/core/test_crypto.py`:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/core/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.crypto'`.

- [ ] **Step 3: Add the CONNECTOR_SECRET_KEY setting**

In `backend/app/core/config.py` add an `import base64` at the top of the file, declare the field next to `SECRET_KEY`:

```python
    CONNECTOR_SECRET_KEY: str
```

and add a validator to the `Settings` class:

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

- [ ] **Step 4: Generate the key and put it into the environment**

Run: `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
Expected: a 44-character string ending in `=`.

Add it to `.env` next to `SECRET_KEY`:

```
CONNECTOR_SECRET_KEY=<the generated value>
```

In `compose.yml`, in the `environment` section of the `backend` service (and `prestart`, if it has its own list of variables), add a line next to `SECRET_KEY`:

```yaml
      CONNECTOR_SECRET_KEY: ${CONNECTOR_SECRET_KEY?Variable not set}
```

- [ ] **Step 5: Implement the encryption module**

Create `backend/app/core/crypto.py`:

```python
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE = 12


def _key() -> bytes:
    return base64.urlsafe_b64decode(settings.CONNECTOR_SECRET_KEY)


def encrypt(plaintext: bytes) -> bytes:
    """Encrypt data. Returns the nonce concatenated with the ciphertext."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(payload: bytes) -> bytes:
    """Decrypt data produced by encrypt().

    Raises cryptography.exceptions.InvalidTag if the data is corrupted
    or was encrypted with a different key.
    """
    nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/core/test_crypto.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 7: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/crypto.py backend/app/core/config.py backend/tests/core compose.yml
git commit -m "feat: encrypt connector credentials with AES-GCM"
```

---

### Task 3: Adapter contract and type registry

**Files:**
- Create: `backend/app/adapters/__init__.py`
- Create: `backend/app/adapters/protocol.py`
- Create: `backend/app/adapters/registry.py`
- Create: `backend/tests/adapters/__init__.py`
- Create: `backend/tests/adapters/conftest.py`
- Create: `backend/tests/adapters/test_registry.py`

**Interfaces:**
- Consumes: nothing beyond the standard library and pydantic.
- Produces:
  - `app.adapters.protocol.ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]`
  - `app.adapters.protocol.ConnectionCheckResult` with fields `ok: bool`, `message: str`, `latency_ms: int | None`, `error_kind: ErrorKind | None`
  - `app.adapters.protocol.DataAdapter` — a Protocol with the method `async def check_connection(self) -> ConnectionCheckResult`
  - `app.adapters.registry.AdapterType` — a frozen dataclass with fields `name`, `title`, `options_schema`, `factory`
  - `app.adapters.registry.register(name, title, options_schema)` — a factory decorator
  - `app.adapters.registry.get(name) -> AdapterType`, raises `UnknownAdapterType`
  - `app.adapters.registry.all_types() -> list[AdapterType]`, sorted by `title`
  - `app.adapters.registry.secret_field_names(schema) -> set[str]`
  - `app.adapters.registry.UnknownAdapterType(Exception)`
  - the `isolated_registry` fixture in `tests/adapters/conftest.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/adapters/__init__.py` as an empty file.

Create `backend/tests/adapters/conftest.py` — a fixture that isolates the registry so registrations made in tests do not leak into other tests:

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

Create `backend/tests/adapters/test_registry.py`:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/adapters/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.adapters'`.

- [ ] **Step 3: Implement the protocol**

Create `backend/app/adapters/__init__.py` as an empty file.

Create `backend/app/adapters/protocol.py`:

```python
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class ConnectionCheckResult(BaseModel):
    """Outcome of a connection check.

    Drivers never let their own exceptions escape: their text
    routinely contains the connection string, password included.
    """

    ok: bool
    message: str
    latency_ms: int | None = None
    error_kind: ErrorKind | None = None


@runtime_checkable
class DataAdapter(Protocol):
    async def check_connection(self) -> ConnectionCheckResult: ...
```

- [ ] **Step 4: Implement the registry**

Create `backend/app/adapters/registry.py`:

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
    """Names of the schema fields declared as SecretStr.

    The single source of truth for which values are to be encrypted.
    """
    return {
        name
        for name, field in schema.model_fields.items()
        if field.annotation is SecretStr
    }
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/adapters/test_registry.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/adapters backend/tests/adapters
git commit -m "feat: adapter contract and source type registry"
```

---

### Task 4: PostgreSQL adapter

**Files:**
- Create: `backend/app/adapters/postgres/__init__.py`
- Create: `backend/app/adapters/postgres/options.py`
- Create: `backend/app/adapters/postgres/adapter.py`
- Create: `backend/tests/adapters/test_postgres.py`
- Modify: `backend/app/adapters/__init__.py`

**Interfaces:**
- Consumes: `registry.register`, `ConnectionCheckResult`, `ErrorKind` from task 3.
- Produces:
  - `app.adapters.postgres.options.PostgresOptions` with fields `host: str`, `port: int = 5432`, `database: str`, `user: str`, `password: SecretStr`
  - `app.adapters.postgres.adapter.PostgresAdapter`, registered under the name `"postgres"` with the title `"PostgreSQL"`
  - `app.adapters.postgres.adapter.CHECK_TIMEOUT_SECONDS = 5.0`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/adapters/test_postgres.py`. The tests run against the same database that `docker compose up -d db` starts, and take its parameters from the application settings:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/adapters/test_postgres.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.adapters.postgres'`.

- [ ] **Step 3: Describe the options schema**

Create `backend/app/adapters/postgres/__init__.py`:

```python
from app.adapters.postgres import adapter  # noqa: F401
```

Create `backend/app/adapters/postgres/options.py`:

```python
from pydantic import BaseModel, Field, SecretStr


class PostgresOptions(BaseModel):
    host: str = Field(title="Host", min_length=1)
    port: int = Field(default=5432, title="Port", ge=1, le=65535)
    database: str = Field(title="Database", min_length=1)
    user: str = Field(title="User", min_length=1)
    password: SecretStr = Field(title="Password")
```

- [ ] **Step 4: Implement the adapter**

Create `backend/app/adapters/postgres/adapter.py`:

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
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text is not passed on: psycopg includes the connection
    string in it, password included.
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

`asyncio.wait_for` raises `TimeoutError` when the timeout expires — since Python 3.11 that is an alias of `asyncio.TimeoutError`, so the check in `_classify` covers both cases.

- [ ] **Step 5: Hook the driver into the package import**

Replace the contents of `backend/app/adapters/__init__.py`:

```python
# Imported for its side effect: drivers register themselves in the registry on import.
from app.adapters import postgres  # noqa: F401
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `docker compose up -d db && cd backend && uv run pytest tests/adapters/ -v`
Expected: PASS, 11 tests (6 from task 3 and 5 new).

- [ ] **Step 7: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/adapters backend/tests/adapters
git commit -m "feat: PostgreSQL adapter with error classification and sanitisation"
```

---

### Task 5: Connector model and migration

**Files:**
- Create: `backend/app/connectors/__init__.py`
- Create: `backend/app/connectors/models.py`
- Create: `backend/app/alembic/versions/<hash>_add_connector.py` (generated)
- Create: `backend/tests/connectors/__init__.py`
- Create: `backend/tests/connectors/test_models.py`
- Modify: `backend/app/alembic/env.py`

**Interfaces:**
- Consumes: `app.models.get_datetime_utc`, `app.models.User` from task 1.
- Produces:
  - `app.connectors.models.Connector` — the `connector` table
  - `app.connectors.models.ConnectorCreate` with fields `name: str`, `adapter_type: str`, `options: dict[str, Any]`
  - `app.connectors.models.ConnectorUpdate` with fields `name: str | None`, `options: dict[str, Any] | None`
  - `app.connectors.models.ConnectorPublic` with fields `id`, `name`, `adapter_type`, `config`, `created_at`, `updated_at`
  - `app.connectors.models.ConnectorsPublic` with fields `data: list[ConnectorPublic]`, `count: int`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/connectors/__init__.py` as an empty file and `backend/tests/connectors/test_models.py`:

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

The `create_random_user` function already exists in `backend/tests/utils/user.py:22` and by this point has been converted to async by task 1, step 12. Its signature must be `async def create_random_user(db: AsyncSession) -> User`.

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/connectors/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors'`.

- [ ] **Step 3: Describe the model and API schemas**

Create `backend/app/connectors/__init__.py` as an empty file.

Create `backend/app/connectors/models.py`:

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
    # A key of the adapter type registry, not a foreign key: the registry lives in code.
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

- [ ] **Step 4: Make the model visible to Alembic**

In `backend/app/alembic/env.py` next to the line `from app.models import SQLModel  # noqa` add:

```python
from app.connectors.models import Connector  # noqa
```

Without this import the table does not get into `SQLModel.metadata`, and autogeneration does not see it.

- [ ] **Step 5: Generate the migration**

Run: `docker compose up -d db && cd backend && uv run alembic revision --autogenerate -m "add connector"`
Expected: a file is created in `backend/app/alembic/versions/`.

Open the created file and check that `upgrade()` contains: creation of the `connector` table, a `config` column of type `JSONB` and a `secrets` column of type `LargeBinary`, a foreign key to `user.id` with `ondelete="CASCADE"`, the `uq_connector_owner_name` constraint. There must be no extra operations (dropping or altering other tables) — if there are, remove them by hand.

- [ ] **Step 6: Apply the migration**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade ... -> <hash>, add connector`.

- [ ] **Step 7: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/connectors/test_models.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 8: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/connectors backend/app/alembic backend/tests/connectors backend/tests/utils
git commit -m "feat: connector model and migration"
```

---

### Task 6: Splitting options into configuration and secrets

**Files:**
- Create: `backend/app/connectors/service.py`
- Create: `backend/tests/connectors/test_service.py`

**Interfaces:**
- Consumes: `registry.get`, `registry.secret_field_names`, `registry.AdapterType` from task 3; `crypto.encrypt`, `crypto.decrypt` from task 2.
- Produces:
  - `app.connectors.service.split_options(adapter_type: AdapterType, options: dict[str, Any]) -> tuple[dict[str, Any], bytes]`
  - `app.connectors.service.merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]`
  - `app.connectors.service.fill_missing_secrets(adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]`
  - `app.connectors.service.build_adapter(adapter_type: AdapterType, options: dict[str, Any]) -> DataAdapter`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/connectors/test_service.py`:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/connectors/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors.service'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/connectors/service.py`:

```python
import json
from typing import Any

from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterType, secret_field_names
from app.core import crypto


def split_options(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Split options into non-secret configuration and encrypted secrets.

    The split follows the schema declaration (which fields are SecretStr), not
    a separate list: forgetting to mark a field is impossible.
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
    """Reassemble the full set of options from configuration and secrets."""
    secrets = json.loads(crypto.decrypt(secrets_blob))
    return {**config, **secrets}


def fill_missing_secrets(
    adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes
) -> dict[str, Any]:
    """Fill in stored secrets for those not supplied.

    Needed both for PATCH and for the connection check while editing:
    the user changes the port without typing the password again.
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

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/connectors/test_service.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors/service.py backend/tests/connectors/test_service.py
git commit -m "feat: split connector options into configuration and encrypted secrets"
```

---

### Task 7: Connector CRUD endpoints

**Files:**
- Create: `backend/app/connectors/crud.py`
- Create: `backend/app/connectors/routes.py`
- Create: `backend/tests/connectors/test_routes.py`
- Modify: `backend/app/api/main.py`

**Interfaces:**
- Consumes: `SessionDep`, `CurrentUser` from task 1; models from task 5; `split_options`, `fill_missing_secrets` from task 6; `registry.get`, `UnknownAdapterType` from task 3.
- Produces:
  - `app.connectors.crud.create(session, *, name: str, adapter_type: str, config: dict[str, Any], secrets: bytes, owner_id: uuid.UUID) -> Connector`
  - `app.connectors.crud.get(session, *, connector_id: uuid.UUID, owner: User) -> Connector | None`
  - `app.connectors.crud.list_for(session, *, owner: User, skip: int, limit: int) -> tuple[list[Connector], int]`
  - `app.connectors.crud.save(session, *, connector: Connector) -> Connector`
  - `app.connectors.crud.delete(session, *, connector: Connector) -> None`
  - the router `app.connectors.routes.router` with the prefix `/connectors`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/connectors/test_routes.py`:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/connectors/test_routes.py -v`
Expected: FAIL — every request returns 404 because the router is not included.

- [ ] **Step 3: Implement database access**

Create `backend/app/connectors/crud.py`:

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
        # Someone else's connector is indistinguishable from a missing one: otherwise
        # enumerating identifiers reveals which connections other users have.
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

- [ ] **Step 4: Implement the endpoints**

Create `backend/app/connectors/routes.py`:

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

- [ ] **Step 5: Include the router**

In `backend/app/api/main.py` add the import and the inclusion:

```python
from app.connectors.routes import router as connectors_router
```

and next to the other `include_router` calls:

```python
api_router.include_router(connectors_router)
```

Importing `app.connectors.routes` pulls in `app.adapters`, so drivers register when the application starts.

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/connectors/test_routes.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 7: Run the whole test suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS in full.

- [ ] **Step 8: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/connectors backend/app/api/main.py backend/tests/connectors
git commit -m "feat: connector CRUD endpoints isolated by owner"
```

---

### Task 8: Adapter type list and connection check

**Files:**
- Create: `backend/app/adapters/routes.py`
- Create: `backend/tests/adapters/test_routes.py`
- Create: `backend/tests/connectors/test_check.py`
- Modify: `backend/app/connectors/routes.py`
- Modify: `backend/app/api/main.py`

**Interfaces:**
- Consumes: everything from tasks 3, 4, 6, 7.
- Produces:
  - `GET /api/v1/adapter-types/` → `list[AdapterTypeInfo]`, where `AdapterTypeInfo` has fields `name: str`, `title: str`, `options_schema: dict[str, Any]`
  - `POST /api/v1/connectors/{connector_id}/check` → `ConnectionCheckResult`
  - `POST /api/v1/connectors/check-draft` → `ConnectionCheckResult`, body `ConnectionCheckRequest` with fields `adapter_type: str`, `options: dict[str, Any]`, `connector_id: uuid.UUID | None`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/adapters/test_routes.py`:

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

Create `backend/tests/connectors/test_check.py`:

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

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd backend && uv run pytest tests/adapters/test_routes.py tests/connectors/test_check.py -v`
Expected: FAIL — the endpoints return 404.

- [ ] **Step 3: Implement the adapter type list**

Create `backend/app/adapters/routes.py`:

```python
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from fastapi import Depends

from app.adapters import registry
from app.api.deps import get_current_user

# Authentication is declared at the router level: the handler itself does not use
# the user, and an unused parameter is forbidden by the ruff rule ARG001.
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

- [ ] **Step 4: Add the connection check endpoints**

In the import block of `backend/app/connectors/routes.py` add the line

```python
from app.adapters.protocol import ConnectionCheckResult
```

and extend the existing pydantic import to

```python
from pydantic import BaseModel, ValidationError
```

Then add at the end of the file:

```python
class ConnectionCheckRequest(BaseModel):
    adapter_type: str
    options: dict[str, Any]
    connector_id: uuid.UUID | None = None


@router.post("/check-draft", response_model=ConnectionCheckResult)
async def check_draft(
    session: SessionDep, current_user: CurrentUser, body: ConnectionCheckRequest
) -> Any:
    """Check the connection from the form data without saving anything.

    If connector_id is given, missing secret fields are taken from the
    stored connector: the user changes the port without typing the password again.
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

- [ ] **Step 5: Include the adapter type router**

In `backend/app/api/main.py` add:

```python
from app.adapters.routes import router as adapter_types_router
```

and next to the others:

```python
api_router.include_router(adapter_types_router)
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd backend && uv run pytest tests/adapters/test_routes.py tests/connectors/test_check.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 7: Run the whole test suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS in full.

- [ ] **Step 8: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/adapters backend/app/connectors backend/app/api/main.py backend/tests
git commit -m "feat: adapter type list and connection check"
```

---

### Task 9: Remove the sample Item entity

Done last: until then `Item` serves as a working example at hand.

**Files:**
- Delete: `backend/app/api/routes/items.py`
- Delete: `backend/tests/api/routes/test_items.py`
- Delete: `backend/tests/utils/item.py`
- Create: `backend/app/alembic/versions/<hash>_drop_item.py` (generated)
- Modify: `backend/app/models.py`, `backend/app/crud.py`, `backend/app/api/main.py`, `backend/app/api/routes/users.py`, `backend/tests/conftest.py`

**Interfaces:**
- Consumes: everything from tasks 1–8.
- Produces: nothing new; removes `Item`, `ItemBase`, `ItemCreate`, `ItemUpdate`, `ItemPublic`, `ItemsPublic`, `crud.create_item`.

- [ ] **Step 1: Remove the items router**

In `backend/app/api/main.py` remove `items` from the `from app.api.routes import ...` import and the line `api_router.include_router(items.router)`.

- [ ] **Step 2: Delete the files**

```bash
git rm backend/app/api/routes/items.py backend/tests/api/routes/test_items.py backend/tests/utils/item.py
```

- [ ] **Step 3: Remove the Item models**

In `backend/app/models.py` remove the classes `ItemBase`, `ItemCreate`, `ItemUpdate`, `Item`, `ItemPublic`, `ItemsPublic`, and also the `items` field from the `User` class:

```python
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)
```

If `Relationship` is no longer used anywhere, remove it from the `sqlmodel` import.

- [ ] **Step 4: Remove crud.create_item**

In `backend/app/crud.py` remove the `create_item` function and the mentions of `Item`, `ItemCreate` in the import from `app.models`.

- [ ] **Step 5: Fix user deletion**

In `backend/app/api/routes/users.py:228` remove the line that deletes the related `Item` rows by hand:

```python
    statement = delete(Item).where(col(Item.owner_id) == user_id)
```

together with the line after it that executes this statement, and also remove `Item` from the import on line 16. If after that `delete` and `col` are no longer used anywhere in the file, remove them from the import too. The database-level cascade remains the only mechanism — `Connector` already relies on it.

- [ ] **Step 6: Fix conftest**

In `backend/tests/conftest.py` remove the `Item` import and the line `await session.execute(delete(Item))`. Add clearing of connectors before users are deleted:

```python
        await session.execute(delete(Connector))
        await session.execute(delete(User))
```

with the import `from app.connectors.models import Connector`.

- [ ] **Step 7: Generate and apply the migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "drop item"`
Expected: a migration file is created, and `upgrade()` contains `op.drop_table("item")`.

Run: `cd backend && uv run alembic upgrade head`
Expected: the migration is applied.

- [ ] **Step 8: Run the whole test suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS in full, no tests about `Item` remain.

- [ ] **Step 9: Check types and style**

Run: `cd backend && uv run mypy app && uv run ruff check app tests`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add -A backend
git commit -m "chore: remove the sample Item entity"
```

---

## Summary

After task 9 the backend provides:

- `GET /api/v1/adapter-types/` — source types with the JSON Schema of their options;
- full CRUD for connectors, isolated by owner;
- `POST /api/v1/connectors/{id}/check` and `POST /api/v1/connectors/check-draft`;
- encryption of credentials, which never leave the server.

The Vue frontend is described by a separate plan: `2026-08-15-connector-registry-frontend.md`.

## Known limitation

`check-draft` by its nature opens a TCP connection to an address sent by the client, which lets an authenticated user map the internal network by response time and error kind. The plan implements mitigations — a hard timeout and uniform error messages. Restricting hosts to an allowlist of addresses is a separate backlog task; the extension point is the `_classify` function and the building of the connection string in `PostgresAdapter._conninfo`.
