"""Draw the example declared references a development stack is meant to show.

A development tool, not part of the API. D106 says a declared reference is a
row of this application's own between two columns no source calls related, and
nothing in a fresh stack demonstrates one: the sample files and the fixture
schema hold a matching slug on purpose, and until somebody draws the line by
hand the feature is invisible.

It makes no connection of its own. What a machine is connected to is the
developer's decision, so this only draws examples between connections that are
already there — a stack whose file source was registered a moment ago gets its
examples on the next start.

Every end is read through the same path the route uses, so an example whose
file has been renamed or whose schema is missing is skipped with a reason
rather than stored as a line that leads nowhere.

    python -m app.seed_references [email]
"""

import asyncio
import logging
import sys
from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import declared
from app.connectors.declared import EndReading, ReferenceEnd
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.users import crud
from app.users.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExampleEnd:
    """One end, named by the kind of source it lives in rather than by an id.

    A development machine's connection ids are made when the developer makes
    the connection, so an example can only say "the file source" and "the
    PostgreSQL source" and be resolved against what is there.
    """

    adapter_type: str
    node_id: str
    column: str


@dataclass(frozen=True)
class Example:
    about: str
    ends: tuple[ExampleEnd, ExampleEnd]


# Two, because two is what makes the point: one line crosses from a database
# to a file in personal storage, and one joins two files that only a person
# knows belong together.
EXAMPLES = (
    Example(
        about="demo_lab.organizations and the accounts file share a slug",
        ends=(
            ExampleEnd("postgres", "demo_lab.organizations", "slug"),
            ExampleEnd("file", "accounts.csv", "slug"),
        ),
    ),
    Example(
        about="the accounts file and the renewals file share a slug",
        ends=(
            ExampleEnd("file", "accounts.csv", "slug"),
            ExampleEnd("file", "renewals.csv", "slug"),
        ),
    ),
)


async def _connections(session: AsyncSession, user: User) -> dict[str, Connector]:
    """The oldest switched-on connection of each source type this user owns.

    The oldest rather than any of them: a developer with three file sources
    should get the same example twice in a row rather than a new one each
    start.
    """
    statement = (
        select(Connector)
        .where(Connector.owner_id == user.id, col(Connector.enabled).is_(True))
        .order_by(col(Connector.created_at))
    )
    found: dict[str, Connector] = {}
    for connector in (await session.exec(statement)).all():
        found.setdefault(connector.adapter_type, connector)
    return found


async def draw(session: AsyncSession, user: User) -> list[str]:
    """Draw every example whose two ends this user can actually reach."""
    connections = await _connections(session, user)
    drawn: list[str] = []
    for example in EXAMPLES:
        readings: list[EndReading] = []
        for end in example.ends:
            connector = connections.get(end.adapter_type)
            if connector is None:
                logger.info(
                    "Skipped example (%s): no %s connection",
                    example.about,
                    end.adapter_type,
                )
                break
            try:
                readings.append(
                    await declared.read_end(
                        session,
                        user,
                        None,
                        ReferenceEnd(
                            connector_id=connector.id,
                            node_id=end.node_id,
                            column=end.column,
                        ),
                    )
                )
            except Exception as reason:  # noqa: BLE001 -- a fixture never stops a start.
                logger.info(
                    "Skipped example (%s): %s.%s could not be read: %s",
                    example.about,
                    end.node_id,
                    end.column,
                    reason,
                )
                break
        if len(readings) != len(example.ends):
            continue
        reference = await declared.create(
            session, author=user, ends=(readings[0], readings[1])
        )
        drawn.append(f"{example.about} ({reference.id})")
    return drawn


async def main(email: str) -> None:
    async with async_session_maker() as session:
        user = await crud.get_user_by_email(session=session, email=email)
        if user is None:
            logger.error("No such user: %s", email)
            raise SystemExit(1)
        drawn = await draw(session, user)
    for line in drawn:
        logger.info("Example reference: %s", line)
    logger.info("Drew %d of %d example references", len(drawn), len(EXAMPLES))


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else settings.FIRST_SUPERUSER
    asyncio.run(main(address), loop_factory=loop_factory)
