"""
config.py

All configuration you'd normally change goes here. No other file needs to be
touched to add a new search - copy a Search(...) object, change the fields, done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from scoring import HardLimits, Weights

CURRENCY = "NOK"

# ---------------------------------------------------------------------------
# Date Flexibility
# ---------------------------------------------------------------------------


@dataclass
class DateWindow:
    """Describes 'somewhere in this period, roughly for this long'.

    Example: entire Sept-Oct transition, 5-9 days, check every 3rd day:
        DateWindow(date(2026, 9, 18), date(2026, 10, 12), [5, 7, 9], step_days=3)
    """

    start: date
    end: date
    """Last possible DEPARTURE date (not return)."""

    trip_lengths: list[int]
    """Number of nights away. Each length is checked for each departure date."""

    step_days: int = 1
    """Check every N-th day in the window. Higher = fewer searches = faster
    execution and less risk of being rate-limited by Google."""

    weekdays: list[int] | None = None
    """Optional: restrict departures to specific weekdays (0 = Monday,
    6 = Sunday). E.g. [3, 4] for Thu/Fri only. None = all days."""

    latest_return: date | None = None
    """Optional: return must happen by this date (e.g., if you need to
    be back at work)."""

    def pairs(self) -> list[tuple[date, date]]:
        """All (departure, return) combinations this window produces."""
        out: list[tuple[date, date]] = []
        d = self.start
        while d <= self.end:
            if self.weekdays is None or d.weekday() in self.weekdays:
                for nights in self.trip_lengths:
                    home = d + timedelta(days=nights)
                    if self.latest_return and home > self.latest_return:
                        continue
                    out.append((d, home))
            d += timedelta(days=self.step_days)
        return out

    @property
    def search_count(self) -> int:
        return len(self.pairs())


# ---------------------------------------------------------------------------
# Pre-defined Rule Sets - use as a starting point, adjust freely
# ---------------------------------------------------------------------------

EUROPE_LIMITS = HardLimits(
    max_price=3500,
    max_stops=2,
    max_total_hours=16,
    min_layover_hours=0.75,
    # 'if journey is longer than X hours, it must cost under Y'
    duration_price_rules=[
        (8, 1800),
        (10, 1000),
        (13, 600),
    ],
    # same, but for longest layover
    layover_price_rules=[
        (5, 1600),
        (9, 900),
    ],
)

LONGHAUL_LIMITS = HardLimits(
    max_price=9500,
    max_stops=2,
    max_total_hours=34,
    min_layover_hours=1.25,  # strengere - du vil ikke bomme på en interkont-overgang
    duration_price_rules=[
        (22, 8000),
        (27, 6500),
        (31, 5000),
    ],
    layover_price_rules=[
        (8, 7500),
        (14, 5500),
    ],
)

# Default weights work for most; override per search if needed.
DEFAULT_WEIGHTS = Weights()

# For long-haul, an extra hour is less critical (you're stuck anyway),
# and long layovers are more normal.
LONGHAUL_WEIGHTS = Weights(
    currency_per_detour_hour=70,
    comfortable_layover_hours=4.0,
    currency_per_long_layover_hour=90,
    overnight_layover_hours=9.0,
)


# ---------------------------------------------------------------------------
# Searches
# ---------------------------------------------------------------------------


@dataclass
class Search:
    name: str
    origins: list[str]
    destinations: list[str]
    window: DateWindow
    limits: HardLimits
    weights: Weights = field(default_factory=Weights)
    adults: int = 1
    seat: str = "economy"
    enabled: bool = True
    top_n: int = 3
    """How many results to send to Telegram for this search."""

    notify_when_empty: bool = True
    """False = stay silent when nothing passes filters (useful for searches
    you leave running for months, like the Japan trip)."""


SEARCHES: list[Search] = [
    Search(
        name="Lisbon – Weekend Getaways",
        origins=["OSL"],
        destinations=["LIS"],
        window=DateWindow(
            start=date(2026, 9, 18),
            end=date(2026, 10, 12),
            trip_lengths=[2, 3],
            step_days=7,
            weekdays=[3, 4, 5],  # Thu/Fri/Sat departures only
        ),
        limits=EUROPE_LIMITS,
        weights=DEFAULT_WEIGHTS,
    ),
    # Example of a long-running search. Set enabled=True when you want it running.
    Search(
        name="Tokyo – Winter Break",
        origins=["OSL"],
        destinations=["HND", "NRT"],
        window=DateWindow(
            start=date(2027, 2, 5),
            end=date(2027, 2, 26),
            trip_lengths=[12, 14],
            step_days=4,
            weekdays=[3, 4, 5],  # Thu/Fri/Sat departures only
        ),
        limits=LONGHAUL_LIMITS,
        weights=LONGHAUL_WEIGHTS,
        enabled=False,
        notify_when_empty=False,  # don't spam daily for half a year
    ),
]


def active_searches() -> list[Search]:
    return [s for s in SEARCHES if s.enabled]
