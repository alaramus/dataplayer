"""The web process's handle on the store, rebuilt when the setting changes."""

import asyncio
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.service import merge_options
from app.metrics import crud
from app.metrics.models import MetricsStoreSetting
from app.metrics.store import MetricsStore, store_url


def options_of(setting: MetricsStoreSetting) -> dict[str, Any]:
    return merge_options(setting.config, setting.secrets)


class StoreHolder:
    def __init__(self) -> None:
        self._store: MetricsStore | None = None
        self._configured_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def get(self, session: AsyncSession) -> MetricsStore | None:
        """The store, migrated, or None when none is configured.

        Raises `StoreUnavailable` when one is configured and does not answer.
        """
        setting = await crud.store_setting(session)
        async with self._lock:
            if setting is None:
                await self._drop()
                return None
            if self._store is not None and self._configured_at == setting.configured_at:
                return self._store
            await self._drop()
            store = MetricsStore(store_url(options_of(setting)))
            try:
                await store.migrate()
            except BaseException:
                await store.aclose()
                raise
            self._store = store
            self._configured_at = setting.configured_at
            return store

    async def aclose(self) -> None:
        async with self._lock:
            await self._drop()

    async def _drop(self) -> None:
        if self._store is not None:
            await self._store.aclose()
        self._store = None
        self._configured_at = None


def get_store_holder(request: Request) -> StoreHolder:
    holder = request.app.state.metrics_stores
    if not isinstance(holder, StoreHolder):
        raise RuntimeError("The application has no metrics store holder; is the lifespan running?")
    return holder


StoreHolderDep = Annotated[StoreHolder, Depends(get_store_holder)]
