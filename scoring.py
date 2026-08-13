"""
scoring.py

Two stages:

1. HARD FILTERS (`disqualify`) - trips that are just nonsensical. These
   disappear entirely, no matter how cheap. Examples: 25-minute layover
   between separate tickets, or 14 hours of travel time for $3000.

2. SOFT RANKING (`effective_cost`) - everything that survives is measured in
   "what this trip actually costs you", in currency units. The price is the
   baseline, then we add a penalty for everything that makes the trip worse:
   extra hours, layovers, inconvenient times. Direct + cheap therefore always
   wins, while a 3-stop marathon trip has to be significantly cheaper to beat it.

   The "dirt cheap" exception: you obviously tolerate more hassle for $400
   than for $2500. So the entire penalty scales down (to as low as 50%) when
   the price approaches the market's bottom for that route on that day.
   See `hassle_scale`.

Reference points (what's "fast" and what's "typical price" for this route)
are calculated from the search results themselves - not hardcoded. This means
the same logic works for both Lisbon (direct ~4.5h) and Tokyo (~13h) without
you needing to recalibrate anything.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from models import TripMetrics


# ---------------------------------------------------------------------------
# Hard Filters
# ---------------------------------------------------------------------------


@dataclass
class HardLimits:
    max_price: float
    """Above this price, the trip never shows, no matter how good."""

    max_stops: int = 2
    """3+ layovers are rarely worth it. Set to 3 if you're tough."""

    max_total_hours: float = 20
    """Absolute cap on travel time."""

    min_layover_hours: float = 0.75
    """Below this you simply won't make the connection (baggage, security,
    and Google doesn't guarantee rebooking if they're separate tickets)."""

    duration_price_rules: list[tuple[float, float]] = field(default_factory=list)
    """(hours, max_price): 'if journey is longer than X hours, it must cost under Y'.
    All are checked - the most restrictive one that applies wins."""

    layover_price_rules: list[tuple[float, float]] = field(default_factory=list)
    """(hours, max_price): same principle, but for longest layover."""


def disqualify(m: TripMetrics, limits: HardLimits) -> str | None:
    """Returns a reason if the trip should be rejected, otherwise None."""
    if m.price > limits.max_price:
        return f"price {m.price:.0f} exceeds ceiling {limits.max_price:.0f}"

    if m.stops > limits.max_stops:
        return f"{m.stops} layovers (max {limits.max_stops})"

    if m.total_hours > limits.max_total_hours:
        return f"{m.total_hours:.1f}h travel time (max {limits.max_total_hours})"

    if m.layovers and m.min_layover < limits.min_layover_hours:
        return f"layover of just {m.min_layover * 60:.0f} min"

    for hours, max_price in limits.duration_price_rules:
        if m.total_hours > hours and m.price > max_price:
            return f"{m.total_hours:.1f}h must cost under {max_price:.0f} (costs {m.price:.0f})"

    for hours, max_price in limits.layover_price_rules:
        if m.max_layover > hours and m.price > max_price:
            return (
                f"{m.max_layover:.1f}h layover must cost under "
                f"{max_price:.0f} (costs {m.price:.0f})"
            )

    return None


# ---------------------------------------------------------------------------
# Soft Ranking
# ---------------------------------------------------------------------------


@dataclass
class Weights:
    """All numbers are in currency units. Read them as: 'how much would I pay
    to avoid this?'"""

    currency_per_detour_hour: float = 110
    """Per hour the journey is longer than the fastest we found."""

    stop_penalties: tuple[float, ...] = (0, 300, 1100, 2600)
    """Penalty per number of layovers: 0 stops free, 1 stop 300,
    2 stops 1100, 3+ stops 2600. The ladder is deliberately steep - two stops
    means twice as many things that could go wrong."""

    tight_layover_hours: float = 1.25
    tight_layover_penalty: float = 450
    """Connections under ~1.25h are stressful even when they technically work."""

    comfortable_layover_hours: float = 3.0
    currency_per_long_layover_hour: float = 130
    """Per hour of layover beyond 3h."""

    overnight_layover_hours: float = 7.0
    overnight_layover_penalty: float = 700
    """A layover long enough that you have to sleep at the airport (or pay
    for a hotel) is its own category of bad."""

    early_departure_before: int = 7
    late_arrival_after: int = 23
    awkward_time_penalty: float = 350
    """Departure before 07 means taxi or night bus; arrival after 23
    means the same on the other end."""

    # "Dirt cheap" scaling
    bargain_hassle_scale: float = 0.5
    """How much of the penalty applies when price is at the market's bottom."""

    bargain_ratio: float = 0.55
    """If price is under 55% of typical price on this route, it's considered
    a bargain and gets full penalty discount. Between bargain and typical price,
    it interpolates smoothly."""


@dataclass
class MarketReference:
    """What's 'fast' and what's 'typical' for this route, calculated from
    today's actual search results."""

    fastest_hours: float
    typical_price: float

    @classmethod
    def from_metrics(cls, all_metrics: list[TripMetrics]) -> "MarketReference":
        if not all_metrics:
            return cls(fastest_hours=0.0, typical_price=1.0)
        return cls(
            fastest_hours=min(m.total_hours for m in all_metrics),
            typical_price=statistics.median(m.price for m in all_metrics) or 1.0,
        )


def hassle_scale(price: float, ref: MarketReference, w: Weights) -> float:
    """1.0 = full penalty. Approaches `bargain_hassle_scale` as price
    approaches the market's bottom for this route."""
    if ref.typical_price <= 0:
        return 1.0
    ratio = price / ref.typical_price
    if ratio <= w.bargain_ratio:
        return w.bargain_hassle_scale
    if ratio >= 1.0:
        return 1.0
    # linear interpolation between bargain level and typical price
    t = (ratio - w.bargain_ratio) / (1.0 - w.bargain_ratio)
    return w.bargain_hassle_scale + t * (1.0 - w.bargain_hassle_scale)


def penalty_breakdown(
    m: TripMetrics, ref: MarketReference, w: Weights
) -> list[tuple[str, float]]:
    """Penalties broken down individually, before bargain scaling. Useful
    for understanding why a trip was ranked as it was."""
    items: list[tuple[str, float]] = []

    detour = max(0.0, m.total_hours - ref.fastest_hours)
    if detour > 0.25:
        items.append((f"+{detour:.1f}h vs fastest", detour * w.currency_per_detour_hour))

    stop_cost = w.stop_penalties[min(m.stops, len(w.stop_penalties) - 1)]
    if stop_cost:
        items.append((f"{m.stops} layover(s)", stop_cost))

    for lay in m.layovers:
        if lay < w.tight_layover_hours:
            items.append((f"tight connection {lay * 60:.0f} min", w.tight_layover_penalty))
        elif lay > w.comfortable_layover_hours:
            extra = (lay - w.comfortable_layover_hours) * w.currency_per_long_layover_hour
            items.append((f"long layover {lay:.1f}h", extra))
            if lay > w.overnight_layover_hours:
                items.append(("overnight at airport", w.overnight_layover_penalty))

    if m.departure and m.departure.hour < w.early_departure_before:
        items.append(
            (f"departure {m.departure.strftime('%H:%M')}", w.awkward_time_penalty)
        )

    if m.arrival_local and m.arrival_local.hour >= w.late_arrival_after:
        items.append(
            (f"arrival {m.arrival_local.strftime('%H:%M')}", w.awkward_time_penalty)
        )

    return items


def effective_cost(m: TripMetrics, ref: MarketReference, w: Weights) -> float:
    """The trip's 'real' cost in currency units. Lower is better."""
    penalties = sum(cost for _, cost in penalty_breakdown(m, ref, w))
    return m.price + penalties * hassle_scale(m.price, ref, w)


def explain(m: TripMetrics, ref: MarketReference, w: Weights) -> str:
    """One line that explains the calculation, for the Telegram message."""
    items = penalty_breakdown(m, ref, w)
    scale = hassle_scale(m.price, ref, w)
    if not items:
        return "no penalties - this is as clean as it gets"
    parts = ", ".join(f"{label} ({cost * scale:+.0f})" for label, cost in items)
    if scale < 1.0:
        parts += f" [bargain discount: penalties count {scale:.0%}]"
    return parts
