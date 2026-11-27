"""A secret's text as a password and the user beside it, read alike by every
provider (D454): JSON read by the keys asked for, anything else the password
whole."""

import json

from app.adapters.cloud import IssuedSecret
from app.adapters.cloud.requests import StoredSecret
from app.adapters.protocol import AdapterError
from app.core.translation import say


def read_secret(text: str, request: StoredSecret) -> IssuedSecret:
    try:
        parsed = json.loads(text)
    except ValueError:
        return IssuedSecret(value=text, expires_at=None)
    if not isinstance(parsed, dict):
        return IssuedSecret(value=text, expires_at=None)
    password = parsed.get(request.password_key)
    if not isinstance(password, str):
        raise AdapterError(
            "config", say("The secret has no {key} to read the password from", key=request.password_key)
        )
    user = parsed.get(request.user_key)
    return IssuedSecret(value=password, expires_at=None, user=user if isinstance(user, str) else None)
