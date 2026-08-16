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

    booking_url: str = ""
    """Direct link to book this flight on Google Flights."""

    @property
    def max_layover(self) -> float:
        return max(self.layovers, default=0.0)

    @property
    def min_layover(self) -> float:
        return min(self.layovers, default=0.0)


def compute_metrics(flight) -> TripMetrics:
    """Convert a SerpApi Google Flights result into TripMetrics."""
    # SerpApi format: flight dict with price, duration, airline info, etc.

    # Extract price (comes as string like "123" or with currency)
    price_str = str(flight.get("price", 0)).replace("$", "").replace(",", "").strip()
    try:
        price = float(price_str)
    except (ValueError, TypeError):
        price = 0.0

    # Extract duration from SerpApi response
    total_hours = 0

    # Try multiple possible duration fields
    for field in ["duration", "total_duration", "flight_duration"]:
        if field in flight:
            duration_val = flight.get(field)
            if isinstance(duration_val, (int, float)):
                total_hours = duration_val / 60 if duration_val > 60 else duration_val
                break
            elif isinstance(duration_val, str) and duration_val:
                # Parse strings like "2h 30m", "2h30m", "120"
                try:
                    if "h" in duration_val.lower():
                        parts = duration_val.lower().split("h")
                        hours = int(parts[0].strip())
                        minutes = 0
                        if len(parts) > 1 and parts[1].strip():
                            min_part = parts[1].replace("m", "").strip()
                            if min_part:
                                minutes = int(min_part)
                        total_hours = hours + minutes / 60
                        break
                    elif duration_val.isdigit():
                        total_hours = int(duration_val) / 60
                        break
                except (ValueError, IndexError, AttributeError):
                    pass

    # Fallback: if still 0, estimate 4-5 hours for short haul (Europe)
    if total_hours == 0:
        total_hours = 4.5

    # Extract flight info
    flights_list = flight.get("flights", [])
    stops = max(0, len(flights_list) - 1)

    # Build route and get airlines
    route_parts = []
    airlines = []
    for f in flights_list:
        if f.get("departure_airport", {}).get("id"):
            route_parts.append(f["departure_airport"]["id"])
        if f.get("airline"):
            airline = f.get("airline", "Unknown")
            if airline not in airlines:
                airlines.append(airline)
    if flights_list and flights_list[-1].get("arrival_airport", {}).get("id"):
        route_parts.append(flights_list[-1]["arrival_airport"]["id"])

    route = "-".join(route_parts) if route_parts else "UNKNOWN"

    # Parse departure and arrival times
    departure_str = flight.get("departure_time", "")
    arrival_str = flight.get("arrival_time", "")

    departure = None
    arrival_local = None

    # Estimate departure/arrival from strings like "8:00 AM" or "5:30 PM"
    try:
        if departure_str:
            dep_time = datetime.strptime(departure_str, "%I:%M %p").time()
            departure = datetime.combine(datetime.now().date(), dep_time)
        if arrival_str:
            arr_time = datetime.strptime(arrival_str, "%I:%M %p").time()
            arrival_local = datetime.combine(datetime.now().date(), arr_time)
    except (ValueError, TypeError):
        pass

    # Extract booking URL (SerpApi provides this)
    booking_url = flight.get("booking_link", "") or flight.get("link", "") or ""

    return TripMetrics(
        price=price,
        total_hours=total_hours,
        flying_hours=total_hours,  # SerpApi doesn't break down flying vs layover time
        layovers=[],  # SerpApi doesn't provide detailed layover info
        stops=stops,
        airlines=airlines if airlines else ["Unknown"],
        departure=departure,
        arrival_local=arrival_local,
        route=route,
        booking_url=booking_url,
    )
