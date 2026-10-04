"""Connector policy and grants for user-authored SQL changes (D160)."""

from app.adapters.query import CHANGING, ExecutionMode, StatementClass
from app.connectors.models import Connector
from app.core.access import Access, at_least

NEEDED: dict[StatementClass, Access] = {
    "read": "read",
    "explain": "read",
    "dml": "write",
    "ddl": "structure",
    # It changes how the source stores what is there, not what is there (D206).
    "maintenance": "write",
}


class WriteRefused(Exception):
    """This statement cannot be run under the connection's policy or grant."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def admit_write(
    *,
    connector: Connector,
    access: Access,
    mode: ExecutionMode,
    kinds: list[StatementClass],
    confirmed_write: bool,
    confirmed_high_risk: bool,
    risky: bool,
) -> None:
    """Check a write against the owner policy, grant and current confirmation."""
    writing = [kind for kind in kinds if kind in CHANGING]
    if not writing:
        return
    if mode == "read":
        raise WriteRefused(422, "A write cannot run in read mode")
    if connector.execution_policy == "read_only":
        raise WriteRefused(403, "The owner of this connection allows reading only")
    for kind in writing:
        needed = NEEDED.get(kind, "own")
        if not at_least(access, needed):
            raise WriteRefused(
                403, f"A {kind} statement needs {needed} access to this connection"
            )
    if connector.execution_policy == "confirm_writes" and not confirmed_write:
        raise WriteRefused(409, "Confirm this write before running it")
    if risky and not confirmed_high_risk:
        raise WriteRefused(
            409, "This run asks for something that cannot be undone; confirm it first"
        )


def admit_transaction(*, connector: Connector, access: Access) -> None:
    """Opening a manual transaction needs write access but no separate unlock."""
    if connector.execution_policy == "read_only":
        raise WriteRefused(403, "The owner of this connection allows reading only")
    if not at_least(access, "write"):
        raise WriteRefused(403, "You have read access to this connection")
