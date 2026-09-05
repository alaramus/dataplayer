from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters import options, registry
from app.adapters.cache import SourceCacheWindows
from app.users.deps import get_current_user

# Authentication is declared on the router: the handler itself does not use the
# user, and an unused argument is rejected by the ruff ARG001 rule.
#
# The tag deliberately has no hyphen: the client generator builds the method
# name by cutting everything up to the first hyphen of the operation id, so the
# tag "adapter-types" would produce typesReadAdapterTypes instead of
# readAdapterTypes.
router = APIRouter(
    prefix="/adapter-types",
    tags=["adapters"],
    dependencies=[Depends(get_current_user)],
)


class AdapterTypeInfo(BaseModel):
    name: str
    title: str
    category: registry.Category
    # Sent rather than looked up on the client: one name for a category, and
    # it is the server's.
    category_title: str
    # How this source's catalog is best shown: walked one level at a time, or
    # expanded in place. A property of the source, so the screen reads it
    # instead of branching on the type's name (D62).
    catalog_shape: registry.CatalogShape
    description: str
    # Derived from the driver, never listed — see registry.capabilities_of.
    capabilities: list[registry.Capability]
    # How long this kind of source keeps its own answers, so the form that
    # offers to re-time a connection can say what it would be changing, and
    # say plainly when there is nothing to change. Null when the source keeps
    # nothing at all (D105).
    cache_windows: SourceCacheWindows | None
    options_schema: dict[str, Any]


@router.get("/", response_model=list[AdapterTypeInfo])
async def read_adapter_types() -> Any:
    """
    List available adapter types: what each one is, what it can do, and the
    JSON Schema of its options.
    """
    return [
        AdapterTypeInfo(
            name=adapter_type.name,
            title=adapter_type.title,
            category=adapter_type.category,
            category_title=registry.category_title(adapter_type.category),
            catalog_shape=adapter_type.catalog_shape,
            description=adapter_type.description,
            capabilities=registry.capabilities_of(adapter_type),
            cache_windows=registry.cache_windows_of(adapter_type),
            options_schema=options.json_schema(adapter_type.options_schema),
        )
        for adapter_type in registry.all_types()
    ]
