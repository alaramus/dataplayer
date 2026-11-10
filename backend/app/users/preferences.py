"""What a user chose for themselves.

Apart from `models.py` because a preference is not identity: it is written by
the person it belongs to and read by whatever the preference is about. A row
exists only once something has been chosen, so the defaults below are the
answer for everybody who never opened the screen.
"""

import uuid
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.translation import Language, as_language, current_language

# How often this user's connections are probed, as a closed set rather than a
# number somebody types. A free field here is a field somebody puts 1 in, and
# the cost of that lands on the servers being probed rather than on this one.
#
# "off" is the absence of an interval rather than a sixth one, the way the
# grid's auto-refresh says it: with it the dots say nothing until the check
# button is pressed, which is the honest state for somebody watching forty
# connections they do not want probed.
CheckInterval = Literal["off", "15s", "30s", "1m", "5m", "15m"]

# The seconds each choice means, and the one place that knows. `None` is "no
# round of its own": nothing falls due, so nothing is probed.
CHECK_SECONDS: dict[CheckInterval, float | None] = {
    "off": None,
    "15s": 15.0,
    "30s": 30.0,
    "1m": 60.0,
    "5m": 300.0,
    "15m": 900.0,
}

DEFAULT_CHECK_INTERVAL: CheckInterval = "15s"

# The themes the interface draws (D196), as `stores/theme.ts` names them. None
# is a choice of its own, as for the language: follow the operating system.
Theme = Literal["light", "paper-light", "dark", "paper", "midnight", "dark-blue", "dark-purple"]
THEMES: tuple[Theme, ...] = get_args(Theme)


# The short tours a person can take after the welcome (D356), as the frontend
# names them. The welcome's own tour stays `welcome_tour_done`.
TourId = Literal["views", "pipeline", "dashboards", "agent"]
TOURS: tuple[TourId, ...] = get_args(TourId)


def as_tours(values: list[str] | None) -> list[TourId]:
    """Stored tours read back, in the order they are offered: one this version
    no longer has is dropped rather than refused."""
    taken = set(values or [])
    return [tour for tour in TOURS if tour in taken]


def as_theme(value: str | None) -> Theme | None:
    """A stored theme read back: one this version no longer draws is the system's."""
    for theme in THEMES:
        if theme == value:
            return theme
    return None



def as_interval(value: str) -> CheckInterval:
    """A stored string read back as a choice.

    A column holds text, and text written by another version of this
    application is not a reason to stop probing or to fail a screen: anything
    unrecognised reads as the default.
    """
    for choice in CHECK_SECONDS:
        if choice == value:
            return choice
    return DEFAULT_CHECK_INTERVAL


def check_seconds(value: str) -> float | None:
    return CHECK_SECONDS[as_interval(value)]


class UserPreferences(SQLModel, table=True):
    """One row per user, written the first time they choose anything."""

    user_id: uuid.UUID = Field(
        primary_key=True, foreign_key="user.id", ondelete="CASCADE"
    )
    # A string in the column and a Literal on the wire, as every other closed
    # set in this application is stored.
    connector_checks: str = Field(default=DEFAULT_CHECK_INTERVAL, max_length=8)
    # The welcome tour was finished or skipped. On the account rather than in
    # a browser, so it opens once for each person, on whatever machine.
    welcome_tour_done: bool = Field(default=False)
    tours_done: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False, server_default="[]")
    )
    language: str | None = Field(default=None, max_length=8)
    theme: str | None = Field(default=None, max_length=16)


class PreferencesPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_checks: CheckInterval
    welcome_tour_done: bool
    tours_done: list[TourId]
    language: Language | None
    theme: Theme | None


class PreferencesUpdate(BaseModel):
    """What is being changed, and nothing about the rest.

    Every field is optional for the reason `UserUpdateMe` has them optional: a
    screen that changes one preference must not have to restate the others, or
    two tabs open on it would undo each other.
    """

    model_config = ConfigDict(extra="forbid")

    connector_checks: CheckInterval | None = None
    welcome_tour_done: bool | None = None
    # One tour taken, added to those already taken: a list sent whole would let
    # two tabs undo each other's.
    tour_done: TourId | None = None
    # Absent leaves it alone; null says "the browser's" and is a value to store.
    language: Language | None = None
    # Absent leaves it alone; null says "the system's".
    theme: Theme | None = None


def _public(stored: UserPreferences | None) -> PreferencesPublic:
    if stored is None:
        return PreferencesPublic(
            connector_checks=DEFAULT_CHECK_INTERVAL,
            welcome_tour_done=False,
            tours_done=[],
            language=None,
            theme=None,
        )
    return PreferencesPublic(
        connector_checks=as_interval(stored.connector_checks),
        welcome_tour_done=stored.welcome_tour_done,
        tours_done=as_tours(stored.tours_done),
        language=as_language(stored.language),
        theme=as_theme(stored.theme),
    )


async def stored_for(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences | None:
    statement = select(UserPreferences).where(UserPreferences.user_id == user_id)
    return (await session.exec(statement)).first()


async def of(session: AsyncSession, user_id: uuid.UUID) -> PreferencesPublic:
    """What this user chose, or what everybody gets before choosing."""
    return _public(await stored_for(session, user_id))


async def set_for(
    session: AsyncSession, user_id: uuid.UUID, update: PreferencesUpdate
) -> PreferencesPublic:
    stored = await stored_for(session, user_id)
    if stored is None:
        stored = UserPreferences(user_id=user_id)
    if update.connector_checks is not None:
        stored.connector_checks = update.connector_checks
    if update.welcome_tour_done is not None:
        stored.welcome_tour_done = update.welcome_tour_done
    if update.tour_done is not None and update.tour_done not in stored.tours_done:
        # A new list, so the JSON column is seen as changed.
        stored.tours_done = [*stored.tours_done, update.tour_done]
    if "language" in update.model_fields_set:
        stored.language = update.language
    if "theme" in update.model_fields_set:
        stored.theme = update.theme
    session.add(stored)
    await session.commit()
    return _public(stored)


async def recipient_language(session: AsyncSession, user_id: uuid.UUID) -> Language:
    """What an email to this person is written in (D227): the language they
    chose, or the one the request that sends it was made in."""
    return (await of(session, user_id)).language or current_language.get()

