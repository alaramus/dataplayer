from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters import registry
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
    options_schema: dict[str, Any]


@router.get("/", response_model=list[AdapterTypeInfo])
async def read_adapter_types() -> Any:
    """
    List available adapter types with the JSON Schema of their options.
    """
    return [
        AdapterTypeInfo(
            name=adapter_type.name,
            title=adapter_type.title,
            options_schema=adapter_type.options_schema.model_json_schema(),
        )
        for adapter_type in registry.all_types()
    ]
