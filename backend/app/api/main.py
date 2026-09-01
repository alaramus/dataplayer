from fastapi import APIRouter

from app.adapters.routes import router as adapter_types_router
from app.connectors import health as connector_health
from app.connectors.routes import router as connectors_router
from app.core.config import settings
from app.realtime.routes import router as realtime_router
from app.shares.routes import router as shares_router
from app.system.routes import router as utils_router
from app.users.auth_routes import router as auth_router
from app.users.private_routes import router as private_router
from app.users.routes import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(utils_router)
# Importing the connectors router pulls in app.adapters, so drivers register
# themselves when the application starts.
api_router.include_router(connectors_router)
api_router.include_router(adapter_types_router)
api_router.include_router(shares_router)
api_router.include_router(realtime_router)

# Imported for its registration: the health topic is about connectors, so it
# lives with them, and the socket learns of it here rather than knowing it.
_ = connector_health.NAME


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private_router)
