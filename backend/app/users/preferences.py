"""What a user chose for themselves.

Apart from `models.py` because a preference is not identity: it is written by
the person it belongs to and read by whatever the preference is about. A row
exists only once something has been chosen, so the defaults below are the
answer for everybody who never opened the screen.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.translation import Language, as_language

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
    language: str | None = Field(default=None, max_length=8)


class PreferencesPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_checks: CheckInterval
    welcome_tour_done: bool
    language: Language | None


class PreferencesUpdate(BaseModel):
    """What is being changed, and nothing about the rest.

    Every field is optional for the reason `UserUpdateMe` has them optional: a
    screen that changes one preference must not have to restate the others, or
    two tabs open on it would undo each other.
    """

    model_config = ConfigDict(extra="forbid")

    connector_checks: CheckInterval | None = None
    welcome_tour_done: bool | None = None
    # Absent leaves it alone; null says "the browser's" and is a value to store.
    language: Language | None = None


def _public(stored: UserPreferences | None) -> PreferencesPublic:
    if stored is None:
        return PreferencesPublic(
            connector_checks=DEFAULT_CHECK_INTERVAL,
            welcome_tour_done=False,
            language=None,
        )
    return PreferencesPublic(
        connector_checks=as_interval(stored.connector_checks),
        welcome_tour_done=stored.welcome_tour_done,
        language=as_language(stored.language),
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
    if "language" in update.model_fields_set:
        stored.language = update.language
    session.add(stored)
    await session.commit()
    return _public(stored)
