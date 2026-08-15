from pydantic import BaseModel, Field, SecretStr


class PostgresOptions(BaseModel):
    host: str = Field(title="Host", min_length=1)
    port: int = Field(default=5432, title="Port", ge=1, le=65535)
    database: str = Field(title="Database", min_length=1)
    user: str = Field(title="User", min_length=1)
    password: SecretStr = Field(title="Password")
