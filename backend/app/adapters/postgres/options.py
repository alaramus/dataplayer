from pydantic import BaseModel, Field, SecretStr

from app.adapters.layout import layout


class PostgresOptions(BaseModel):
    host: str = Field(title="Host", min_length=1, json_schema_extra=layout(row="address"))
    port: int = Field(
        default=5432,
        title="Port",
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    database: str = Field(title="Database", min_length=1, json_schema_extra=layout())
    user: str = Field(title="User", min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title="Password", json_schema_extra=layout())
