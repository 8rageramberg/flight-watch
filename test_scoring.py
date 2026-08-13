"""
test_scoring.py

Tests the logic against fictional (but realistic and some deliberately absurd)
trips, so you can change weights and rules without having to wait for a real
Google search to see the effect.

    python test_scoring.py
"""

from __future__ import annotations

from datetime import date

from config import EUROPE_LIMITS, LONGHAUL_LIMITS, LONGHAUL_WEIGHTS, DateWindow
from models import TripMetrics
from scoring import (
    MarketReference,
    Weights,
    disqualify,
    effective_cost,
    explain,
    hassle_scale,
)


def trip(
    price,
    flying_hours,
    layovers=(),
    dep_hour=10,
    arr_hour=15,
    airlines=("SK",),
    route="OSL-LIS",
):
    """Build TripMetrics directly, without going through Google."""
    from datetime import datetime

    layovers = list(layovers)
    return TripMetrics(
        price=price,
        total_hours=flying_hours + sum(layovers),
        flying_hours=flying_hours,
        layovers=layovers,
        stops=len(layovers),
        airlines=list(airlines),
        departure=datetime(2026, 9, 21, dep_hour, 0),
        arrival_local=datetime(2026, 9, 21, arr_hour, 0),
        route=route,
    )


# ---------------------------------------------------------------------------
# Test Trips to Lisbon - from reasonable to absurd
# ---------------------------------------------------------------------------

EUROPE_TRIPS = {
    "direct, expensive": trip(3100, 4.5, route="OSL-LIS"),
    "direct, fair price": trip(2400, 4.5, route="OSL-LIS"),
    "1 stop, good connection": trip(1750, 5.5, [2.0], route="OSL-AMS-LIS"),
    "1 stop, cheap": trip(1250, 5.8, [2.5], route="OSL-CPH-LIS"),
    "1 stop, tight 40 min connection": trip(1100, 5.5, [0.67], route="OSL-FRA-LIS"),
    "1 stop, 6h wait": trip(1150, 5.5, [6.0], route="OSL-MUC-LIS"),
    "2 stops, bargain": trip(680, 7.0, [1.5, 2.0], route="OSL-BER-MAD-LIS"),
    "2 stops, expensive and slow": trip(2900, 8.0, [3.0, 3.0], route="OSL-LHR-MAD-LIS"),
    "3 stops, absurd": trip(520, 9.0, [2.0, 1.5, 3.0], route="OSL-RIX-WAW-MAD-LIS"),
    "nightmare: 11h, 9h wait": trip(
        890, 6.0, [9.0], dep_hour=5, arr_hour=23, route="OSL-IST-LIS"
    ),
    "early direct": trip(1900, 4.5, dep_hour=5, route="OSL-LIS"),
}


def show(title, trips, limits, weights):
    print("=" * 78)
    print(title)
    print("=" * 78)

    metrics = list(trips.values())
    ref = MarketReference.from_metrics(metrics)
    print(
        f"Reference: fastest {ref.fastest_hours:.1f}h, "
        f"typical price {ref.typical_price:.0f}\n"
    )

    print("--- REJECTED BY HARD FILTERS ---")
    survivors = []
    for name, m in trips.items():
        reason = disqualify(m, limits)
        if reason:
            print(f"  ✗ {name:<34} {reason}")
        else:
            survivors.append((name, m))
    if len(survivors) == len(trips):
        print("  (none)")

    print("\n--- RANKED (lowest weighted cost wins) ---")
    survivors.sort(key=lambda x: effective_cost(x[1], ref, weights))
    for i, (name, m) in enumerate(survivors, start=1):
        cost = effective_cost(m, ref, weights)
        scale = hassle_scale(m.price, ref, weights)
        print(
            f"  {i}. {name:<34} {m.price:>5.0f} → weighted {cost:>6.0f}  "
            f"({m.total_hours:.1f}h, {m.stops} stops, penalty scale {scale:.0%})"
        )
        print(f"       {explain(m, ref, weights)}")
    print()


def test_europe():
    show("LISBOA (EUROPE_LIMITS)", EUROPE_TRIPS, EUROPE_LIMITS, Weights())


def test_longhaul():
    trips = {
        "1 stop, 19h, expensive": trip(
            8200, 15.0, [4.0], airlines=("LH",), route="OSL-FRA-HND"
        ),
        "1 stop, 21h, fair": trip(
            6400, 15.5, [5.5], airlines=("AY",), route="OSL-HEL-NRT"
        ),
        "2 stops, 28h, cheap": trip(
            4700, 17.0, [5.0, 6.0], airlines=("TK",), route="OSL-IST-BKK-HND"
        ),
        "2 stops, 28h, expensive": trip(
            7900, 17.0, [5.0, 6.0], airlines=("QR",), route="OSL-DOH-SIN-HND"
        ),
        "1 stop, 30h overnight": trip(
            5200, 16.0, [14.0], airlines=("CA",), route="OSL-PEK-NRT"
        ),
        "1 stop, 1h connection": trip(
            6100, 15.0, [1.0], airlines=("KL",), route="OSL-AMS-HND"
        ),
    }
    show("TOKYO (LONGHAUL_LIMITS)", trips, LONGHAUL_LIMITS, LONGHAUL_WEIGHTS)


def test_date_window():
    print("=" * 78)
    print("DATE WINDOW")
    print("=" * 78)

    w = DateWindow(date(2026, 9, 18), date(2026, 10, 12), [5, 7, 9], step_days=2)
    print(f"Flexible Sept/Oct, every 2nd day, 5/7/9 nights: {w.search_count} searches")
    print(f"  first: {w.pairs()[0]}   last: {w.pairs()[-1]}")

    w2 = DateWindow(
        date(2026, 9, 18), date(2026, 10, 12), [5, 7, 9], step_days=1, weekdays=[3, 4]
    )
    print(f"Thu/Fri departures only, every day: {w2.search_count} searches")

    w3 = DateWindow(
        date(2026, 9, 18),
        date(2026, 10, 12),
        [5, 7, 9],
        step_days=2,
        latest_return=date(2026, 10, 15),
    )
    print(f"Must return by Oct 15: {w3.search_count} searches")
    print()


def test_sanity_assertions():
    """Some assertions that should hold regardless of weight tuning."""
    ref = MarketReference.from_metrics(list(EUROPE_TRIPS.values()))
    w = Weights()

    cheap_direct = trip(1200, 4.5)
    same_price_two_stops = trip(1200, 7.0, [1.5, 2.0])
    assert effective_cost(cheap_direct, ref, w) < effective_cost(
        same_price_two_stops, ref, w
    ), "direct must beat 2 stops at same price"

    # A big enough price difference should justify a layover
    expensive_direct = trip(3000, 4.5)
    cheap_one_stop = trip(1100, 5.5, [2.0])
    assert effective_cost(cheap_one_stop, ref, w) < effective_cost(
        expensive_direct, ref, w
    ), "1900 saved must outweigh one stop"

    # The bargain discount should actually kick in
    assert hassle_scale(600, ref, w) < hassle_scale(2400, ref, w)

    # Hard filters
    assert disqualify(trip(1100, 5.5, [0.5]), EUROPE_LIMITS), "too tight connection"
    assert disqualify(trip(2500, 9.0, [2.0, 3.0]), EUROPE_LIMITS), "long AND expensive"
    assert disqualify(trip(5000, 4.5), EUROPE_LIMITS), "exceeds price cap"
    assert not disqualify(trip(1750, 5.5, [2.0]), EUROPE_LIMITS), "this one is fine"

    print("✓ All sanity checks passed\n")


if __name__ == "__main__":
    test_date_window()
    test_europe()
    test_longhaul()
    test_sanity_assertions()
