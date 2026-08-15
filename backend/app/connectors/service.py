import json
from typing import Any

from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterType, secret_field_names
from app.core import crypto


def split_options(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Разделить опции на несекретную конфигурацию и зашифрованные секреты.

    Разделение выполняется по объявлению схемы — какие поля объявлены как
    SecretStr, — а не по отдельному списку: забыть пометить поле невозможно.
    """
    model = adapter_type.options_schema.model_validate(options)
    secret_names = secret_field_names(adapter_type.options_schema)
    dumped = model.model_dump(mode="json")

    config = {name: value for name, value in dumped.items() if name not in secret_names}
    secrets = {
        name: getattr(model, name).get_secret_value()
        for name in secret_names
        if getattr(model, name) is not None
    }
    return config, crypto.encrypt(json.dumps(secrets).encode())


def merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]:
    """Собрать полный набор опций обратно из конфигурации и секретов."""
    secrets = json.loads(crypto.decrypt(secrets_blob))
    return {**config, **secrets}


def fill_missing_secrets(
    adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes
) -> dict[str, Any]:
    """Подставить сохранённые секреты вместо непереданных.

    Нужно и для PATCH, и для проверки соединения при редактировании:
    пользователь правит порт, не вводя пароль заново.
    """
    stored = json.loads(crypto.decrypt(secrets_blob))
    filled = dict(options)
    for name in secret_field_names(adapter_type.options_schema):
        if not filled.get(name) and name in stored:
            filled[name] = stored[name]
    return filled


def build_adapter(adapter_type: AdapterType, options: dict[str, Any]) -> DataAdapter:
    model = adapter_type.options_schema.model_validate(options)
    return adapter_type.factory(model)
