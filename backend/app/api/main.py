from fastapi import APIRouter

from app.adapters.routes import router as adapter_types_router
from app.api.routes import items, login, private, users, utils
from app.connectors.routes import router as connectors_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
# Импорт роутера тянет за собой app.adapters, поэтому драйверы регистрируются
# в реестре при старте приложения.
api_router.include_router(connectors_router)
api_router.include_router(adapter_types_router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
