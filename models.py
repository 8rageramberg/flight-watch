"""
models.py

Data structures + calculation of "metrics" for a single trip.

Important detail: total travel time is NOT calculated as (arrival - departure),
because that fails as soon as you cross time zones (OSL -> Tokyo would look like
6 hours). Instead, each flight segment's own duration (as Google reports it in
minutes) is summed, plus the layovers. Layovers can safely be calculated as
(next departure - previous arrival), since both happen at the same airport and
thus in the same time zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TripMetrics:
    """Everything we need to know about a single trip to evaluate it."""

    price: float
    total_hours: float
    """Actual travel time: sum of flight time + layovers."""

    flying_hours: float
    layovers: list[float] = field(default_factory=list)
    """Duration in hours for each layover."""

    stops: int = 0
    airlines: list[str] = field(default_factory=list)

    departure: datetime | None = None
    arrival_local: datetime | None = None
    """Arrival time in destination's local time (as Google reports it)."""

    route: str = ""
    """E.g., 'OSL-AMS-LIS'."""

    @property
    def max_layover(self) -> float:
        return max(self.layovers, default=0.0)

    @property
    def min_layover(self) -> float:
        return min(self.layovers, default=0.0)


def _to_datetime(sd) -> datetime:
    """fast-flights provides dates/times as tuples: (year, month, day) and (hour, minute)."""
    y, mo, da = sd.date
    h, mi = sd.time
    return datetime(y, mo, da, h, mi)


def compute_metrics(flight) -> TripMetrics:
    """Convert a `fast_flights.model.Flights` object into TripMetrics."""
    legs = flight.flights

    flying_minutes = sum(leg.duration or 0 for leg in legs)

    layovers: list[float] = []
    for i in range(len(legs) - 1):
        gap = _to_datetime(legs[i + 1].departure) - _to_datetime(legs[i].arrival)
        layovers.append(gap.total_seconds() / 3600)

    flying_hours = flying_minutes / 60
    total_hours = flying_hours + sum(layovers)

    route = legs[0].from_airport.code
    for leg in legs:
        route += f"-{leg.to_airport.code}"

    return TripMetrics(
        price=flight.price,
        total_hours=total_hours,
        flying_hours=flying_hours,
        layovers=layovers,
        stops=len(legs) - 1,
        airlines=list(flight.airlines),
        departure=_to_datetime(legs[0].departure),
        arrival_local=_to_datetime(legs[-1].arrival),
        route=route,
    )
