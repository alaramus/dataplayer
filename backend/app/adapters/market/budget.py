"""An exchange's rate limit, kept under its ceiling (D316, D425).

The mechanism is shared; the numbers are each exchange's: the limit, the
window it is counted over, what a request weighs, and whether the exchange
reports what was used. A window is counted from its start, as Binance counts
a minute. A request that would pass the ceiling is refused unsent, and a
refusal by the exchange holds every request until the time it names.
"""

from dataclasses import dataclass

CEILING_SHARE = 0.8


class OverBudget(Exception):
    """A request would pass the ceiling; `seconds` until the window turns."""

    def __init__(self, seconds: int) -> None:
        super().__init__(seconds)
        self.seconds = seconds


class Held(Exception):
    """The exchange refuses this address for `seconds` more."""

    def __init__(self, seconds: int) -> None:
        super().__init__(seconds)
        self.seconds = seconds


@dataclass
class Budget:
    limit: int
    window_seconds: int = 60
    # Of the limit, the share spent at most in one window; the rest is left
    # for whatever else asks from the same address.
    share: float = CEILING_SHARE
    used: int = 0
    # The window `used` was counted in, as whole windows since the epoch.
    window: int = -1
    held_until: float = 0.0

    @property
    def ceiling(self) -> int:
        return int(self.limit * self.share)

    def window_of(self, now: float) -> int:
        return int(now // self.window_seconds)

    def used_at(self, now: float) -> int:
        return self.used if self.window == self.window_of(now) else 0

    def seconds_left(self, now: float) -> int:
        return max(1, self.window_seconds - int(now % self.window_seconds))

    def admit(self, weight: int, now: float) -> int:
        """What was used before this request, or a refusal before it is sent."""
        if self.held_until > now:
            raise Held(int(self.held_until - now) + 1)
        used = self.used_at(now)
        if used + weight > self.limit * self.share:
            raise OverBudget(self.seconds_left(now))
        return used

    def count(self, before: int, weight: int, now: float, reported: int | None) -> None:
        """The answer's own count where the exchange says one, else ours."""
        self.used = reported if reported is not None else before + weight
        self.window = self.window_of(now)

    def hold(self, until: float) -> None:
        self.held_until = until
