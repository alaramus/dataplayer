from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

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
