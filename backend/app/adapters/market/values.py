"""Values as an exchange writes them (D318, D425).

A decimal stays the exchange's text, checked to be a number and never passed
through a float; a time arrives in milliseconds, as a number or as digits,
and leaves as a moment in UTC.
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from app.core.translation import say


def decimal_text(value: Any) -> str | None:
    """A number as the exchange wrote it, checked to be one; never through a float."""
    if value is None:
        return None
    text = str(value)
    try:
        Decimal(text)
    except InvalidOperation:
        return None
    return text


def whole_of(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def milliseconds(value: Any) -> int | None:
    """A whole number written as a number or as digits, as Bybit writes times."""
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return whole_of(value)


def moment(milliseconds: int | None) -> str | None:
    if milliseconds is None:
        return None
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def boolean_of(value: Any) -> str | None:
    return None if not isinstance(value, bool) else ("true" if value else "false")


def whole_number(column: str, text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(say("{column} takes a whole number", column=column)) from None


def in_quote(contracts: Any, contract_size: int | None) -> str | None:
    """A count of contracts as what they are worth in the quote asset (D321).

    Exact: a contract is a whole number of the quote asset, so nothing is
    divided and nothing rounds.
    """
    text = decimal_text(contracts)
    if text is None or contract_size is None:
        return None
    return str(Decimal(text) * contract_size)


def difference(last: str | None, before: str | None) -> str | None:
    """How far a price moved, exact."""
    if last is None or before is None:
        return None
    # Written out, never as `1E-8`.
    return format(Decimal(last) - Decimal(before), "f")


def percent_change(last: str | None, before: str | None) -> str | None:
    """The change since an earlier price as a percent, to three places (D433).

    For an exchange that sends no percent: the one division in the feeds,
    rounded half to even and never through a float.
    """
    if last is None or before is None:
        return None
    try:
        opened = Decimal(before)
        if opened == 0:
            return None
        change = (Decimal(last) - opened) * 100 / opened
    except InvalidOperation:
        return None
    return str(change.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN))
