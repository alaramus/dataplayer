"""A refusal the server names with a code and the browser words (D225).

The English sentence is still sent: logs, the agent's tools and anybody calling
the API read it. The browser shows it as it is in English and words the code
itself in any other language, so the translation lives once, beside the
screens, and the English lives once, here.
"""

from typing import Literal, get_args

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

# Every code the server answers with. A closed set so the browser's
# dictionaries are typed against it: a code added here and not translated
# there fails `bun run type-check` rather than showing English in Russian.
ProblemCode = Literal[
    "auth.wrong_credentials",
    "auth.inactive_user",
    "auth.invalid_token",
    "auth.not_signed_in",
    "auth.not_enough_privileges",
    "auth.no_user_with_email",
    "users.email_taken",
    "users.not_found",
    "users.wrong_password",
    "users.same_password",
    "users.superuser_cannot_delete_self",
]

# The English for each code. `{name}` takes a parameter by name, the syntax
# the browser's dictionaries use too.
MESSAGES: dict[ProblemCode, str] = {
    "auth.wrong_credentials": "Incorrect email or password",
    "auth.inactive_user": "Inactive user",
    "auth.invalid_token": "Invalid token",
    "auth.not_signed_in": "Could not validate credentials",
    "auth.not_enough_privileges": "The user doesn't have enough privileges",
    "auth.no_user_with_email": "The user with this email does not exist in the system",
    "users.email_taken": "A user with this email already exists",
    "users.not_found": "User not found",
    "users.wrong_password": "Incorrect password",
    "users.same_password": "New password cannot be the same as the current one",
    "users.superuser_cannot_delete_self": "Super users are not allowed to delete themselves",
}

PROBLEM_CODES: tuple[ProblemCode, ...] = get_args(ProblemCode)

# A parameter is data — a name, a number — and never a word to be translated:
# a word inside a parameter would reach a Russian sentence in English.
ProblemParam = str | int | float


class ProblemDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ProblemCode
    params: dict[str, ProblemParam]
    message: str


class ProblemResponse(BaseModel):
    """What a refusal's body is: FastAPI puts an HTTPException's detail under
    `detail`."""

    detail: ProblemDetail


class Problem(HTTPException):
    """An HTTPException whose detail is a code, its parameters and the English."""

    def __init__(
        self,
        status_code: int,
        code: ProblemCode,
        *,
        headers: dict[str, str] | None = None,
        **params: ProblemParam,
    ) -> None:
        self.code: ProblemCode = code
        self.params = params
        detail = ProblemDetail(
            code=code, params=params, message=MESSAGES[code].format(**params)
        )
        super().__init__(
            status_code=status_code, detail=detail.model_dump(), headers=headers
        )
