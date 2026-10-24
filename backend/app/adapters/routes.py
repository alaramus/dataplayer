from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters import options, registry
from app.adapters.cache import SourceCacheWindows
from app.adapters.protocol import MakesSourceHere
from app.core.translation import say, say_schema
from app.guide import reader as guide
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
    # What a screen switches on; what a person reads is the two lists below.
    capabilities: list[registry.Capability]
    # The guide's page about this type, and the short lists it opens with,
    # read from that page so the catalog and the guide say one thing (D183).
    guide: str
    can_see: list[str]
    can_change: list[str]
    # How long this kind of source keeps its own answers, so the form that
    # offers to re-time a connection can say what it would be changing, and
    # say plainly when there is nothing to change. Null when the source keeps
    # nothing at all (D105).
    cache_windows: SourceCacheWindows | None
    options_schema: dict[str, Any]
    # Whether a new source of this type can be made here without starting
    # anything — a SQLite file (D263). Read off the driver, like the rest.
    makes_here: bool = False


# A plain function: the first call reads the guide's pages from disk, and
# FastAPI runs a plain handler in its thread pool.
@router.get("/", response_model=list[AdapterTypeInfo])
def read_adapter_types() -> Any:
    """
    List available adapter types: what each one is, what it can do, and the
    JSON Schema of its options.
    """
    return [info(adapter_type) for adapter_type in registry.all_types()]


def info(adapter_type: registry.AdapterType) -> AdapterTypeInfo:
    key = guide.source_page_key(adapter_type.name)
    page = guide.page(key)
    markdown = page.markdown if page is not None else ""
    return AdapterTypeInfo(
        name=adapter_type.name,
        title=say(adapter_type.title),
        category=adapter_type.category,
        category_title=say(registry.CATEGORY_TITLES[adapter_type.category]),
        catalog_shape=adapter_type.catalog_shape,
        description=say(adapter_type.description),
        capabilities=registry.capabilities_of(adapter_type),
        guide=key,
        can_see=guide.bullets(markdown, guide.CAN_SEE),
        can_change=guide.bullets(markdown, guide.CAN_CHANGE),
        cache_windows=registry.cache_windows_of(adapter_type),
        options_schema=say_schema(options.json_schema(adapter_type.options_schema)),
        makes_here=issubclass(adapter_type.adapter_class, MakesSourceHere),
    )
