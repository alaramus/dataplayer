from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from app.users.bootstrap import init_db


async def test_init_db_creates_the_home_of_an_existing_superuser(
    db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The superuser predates this feature, so creating a user is not enough."""
    monkeypatch.setattr(storage.settings, "USER_STORAGE_ROOT", tmp_path)

    await init_db(db)

    user = await crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert user is not None
    assert storage.home_dir(user.id).is_dir()
