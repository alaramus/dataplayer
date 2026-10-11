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
    "connectors.not_found",
    "connectors.disabled",
    "connectors.content_not_found",
    "connectors.download_not_found",
    "connectors.export_not_found",
    "connectors.range_not_satisfiable",
    "connectors.file_changed",
    "connectors.row_changed",
    "connectors.rows_changed",
    "connectors.import_too_many_rows",
    "access.needs_read",
    "access.needs_write",
    "access.needs_structure",
    "access.needs_own",
    "access.grant_not_found",
    "actions.unknown",
    "actions.not_for_node",
    "actions.needs_read",
    "actions.needs_write",
    "actions.needs_structure",
    "actions.needs_own",
    "actions.unknown_row_command",
    "actions.not_offered",
    "actions.node_repeated",
    "actions.no_node",
    "actions.not_bulk",
    "actions.one_node_at_a_time",
    "actions.no_connector",
    "actions.other_transport",
    "actions.no_preview",
    "actions.no_download",
    "actions.no_file",
    "actions.params_not_json",
    "actions.params_not_object",
    "actions.plan_not_reviewed",
    "declared.not_found",
    "ssh_keys.not_found",
    "ssh_keys.in_use",
    "ssh_keys.no_passphrase",
    "paste.same_connection",
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
    "connectors.not_found": "Connector not found",
    "connectors.disabled": "Connector is disabled",
    "connectors.content_not_found": "Content not found",
    "connectors.download_not_found": "Download not found",
    "connectors.export_not_found": "Export not found",
    "connectors.range_not_satisfiable": "Requested range not satisfiable",
    "connectors.file_changed": "The file changed or was deleted; reload it and try again",
    "connectors.row_changed": "The row changed or was deleted; reload it and try again",
    "connectors.rows_changed": "One or more rows changed or were deleted; reload and try again",
    "connectors.import_too_many_rows": "A new table may be filled with at most {limit} rows",
    "access.needs_read": "This needs read access to the connection",
    "access.needs_write": "This needs write access to the connection",
    "access.needs_structure": "This needs structure access to the connection",
    "access.needs_own": "This needs own access to the connection",
    "access.grant_not_found": "Grant not found",
    "actions.unknown": "Unknown action: {name}",
    "actions.not_for_node": "{action} cannot be done to this node",
    "actions.needs_read": "{action} needs read access",
    "actions.needs_write": "{action} needs write access",
    "actions.needs_structure": "{action} needs structure access",
    "actions.needs_own": "{action} needs own access",
    "actions.unknown_row_command": "Unknown row command: {name}",
    "actions.not_offered": "Nothing called {name} is offered here",
    "actions.node_repeated": "A node may be selected only once",
    "actions.no_node": "Choose a node",
    "actions.not_bulk": "{action} cannot be done in bulk",
    "actions.one_node_at_a_time": "{action} is done to one node at a time",
    "actions.no_connector": "{action} does not prepare a connector",
    "actions.other_transport": "{action} uses a different request transport",
    "actions.no_preview": "{action} cannot say what it would do",
    "actions.no_download": "{action} does not produce a download",
    "actions.no_file": "{action} does not take a file",
    "actions.params_not_json": "The params field is not valid JSON",
    "actions.params_not_object": "The params field must be an object",
    "actions.plan_not_reviewed": "Review the operation plan before running it",
    "declared.not_found": "Declared reference not found",
    "ssh_keys.not_found": "Key not found",
    "ssh_keys.in_use": "This key is used by {names}; point them at another key first",
    "ssh_keys.no_passphrase": "This key does not ask for a passphrase",
    "paste.same_connection": "Pair two different connections",
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
