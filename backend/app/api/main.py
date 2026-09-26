from fastapi import APIRouter

from app.adapters.routes import router as adapter_types_router
from app.ai import topic as agent_topic
from app.ai.routes import router as agent_router
from app.connectors import health as connector_health
from app.connectors.declared_routes import router as declared_references_router
from app.connectors.paste.routes import router as paste_router
from app.connectors.routes import router as connectors_router
from app.connectors.ssh_key_routes import router as ssh_keys_router
from app.connectors.table_routes import router as tables_router
from app.core.config import settings
from app.jobs.routes import router as jobs_router
from app.metrics import live as metrics_live
from app.metrics.routes import router as metrics_router
from app.queries.routes import router as queries_router
from app.realtime.routes import router as realtime_router
from app.services.backup_routes import router as backups_router
from app.services.routes import router as services_router
from app.shares.routes import router as shares_router
from app.source_operations.routes import router as source_operations_router
from app.system.routes import router as utils_router
from app.terminals.routes import router as terminals_router
from app.transfers.routes import router as transfers_router
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
api_router.include_router(declared_references_router)
api_router.include_router(paste_router)
api_router.include_router(tables_router)
api_router.include_router(ssh_keys_router)
api_router.include_router(adapter_types_router)
api_router.include_router(services_router)
api_router.include_router(backups_router)
api_router.include_router(jobs_router)
api_router.include_router(source_operations_router)
api_router.include_router(transfers_router)
api_router.include_router(shares_router)
api_router.include_router(queries_router)
api_router.include_router(metrics_router)
api_router.include_router(agent_router)
api_router.include_router(realtime_router)
api_router.include_router(terminals_router)

# Imported for its registration: the health topic is about connectors, so it
# lives with them, and the socket learns of it here rather than knowing it.
_ = connector_health.NAME
_ = metrics_live.NAME
_ = agent_topic.NAME


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private_router)
