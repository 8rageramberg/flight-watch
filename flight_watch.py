"""
flight_watch.py

Main script. Run locally to test:

    pip install -r requirements.txt
    TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python flight_watch.py

Dry run without sending to Telegram:

    python flight_watch.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

from fast_flights import FlightData, Passengers, get_flights

from config import CURRENCY, Search, active_searches
from models import compute_metrics
from notify import Hit, format_search_message, send_telegram
from scoring import MarketReference, disqualify, effective_cost

STATE_FILE = Path("state.json")

# Small random pause between each search. Google doesn't like 30 requests
# in a row from the same IP, and GitHub Actions runs from shared datacenter IPs.
SLEEP_BETWEEN_SEARCHES = (1.5, 4.0)


# ---------------------------------------------------------------------------
# State (for "X cheaper than last time")
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            print("[!] state.json was corrupted - starting fresh", file=sys.stderr)
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def query_one(
    search: Search, origin: str, dest: str, out_date: date, home_date: date
) -> list:
    try:
        flights = get_flights(
            flight_data=[
                FlightData(date=out_date.isoformat(), from_airport=origin, to_airport=dest),
                FlightData(date=home_date.isoformat(), from_airport=dest, to_airport=origin),
            ],
            trip="round-trip",
            seat=search.seat,
            passengers=Passengers(adults=search.adults),
            fetch_mode='fallback',
        )
        result = list(flights)
        if result:
            print(f"      → found {len(result)} flights")
        else:
            print(f"      → no flights found", file=sys.stderr)
        return result
    except Exception as exc:
        print(f"  [!] {origin}->{dest} {out_date}: {type(exc).__name__}: {str(exc)[:100]}", file=sys.stderr)
        return []


def run_search(search: Search) -> tuple[list[Hit], MarketReference, int, int]:
    """Returns (passing results, market reference, total searches, rejected count)."""
    all_metrics = []
    candidates: list[Hit] = []
    rejected = 0
    searched = 0

    pairs = search.window.pairs()
    total = len(pairs) * len(search.origins) * len(search.destinations)
    print(f"\n=== {search.name}: {total} date combinations ===")

    for origin in search.origins:
        for dest in search.destinations:
            for out_date, home_date in pairs:
                searched += 1
                print(f"  [{searched}/{total}] {origin}->{dest} {out_date} → {home_date}")

                for flight in query_one(search, origin, dest, out_date, home_date):
                    m = compute_metrics(flight)
                    all_metrics.append(m)
                    candidates.append(Hit(m, out_date, home_date, origin, dest))

                time.sleep(random.uniform(*SLEEP_BETWEEN_SEARCHES))

    # Reference points are calculated from EVERYTHING we found, including what's
    # later rejected - otherwise we'd get a skewed picture of what's "fast" and
    # "typical" on this route.
    ref = MarketReference.from_metrics(all_metrics)

    hits: list[Hit] = []
    for hit in candidates:
        reason = disqualify(hit.metrics, search.limits)
        if reason:
            rejected += 1
            continue
        hits.append(hit)

    hits.sort(key=lambda h: effective_cost(h.metrics, ref, search.weights))
    return hits, ref, searched, rejected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="write messages to terminal instead of sending them",
    )
    parser.add_argument(
        "--only",
        help="run only the search with this name (partial match works)",
    )
    args = parser.parse_args()

    state = load_state()
    searches = active_searches()

    if args.only:
        searches = [s for s in searches if args.only.lower() in s.name.lower()]
        if not searches:
            print(f"Found no active searches matching {args.only!r}", file=sys.stderr)
            sys.exit(1)

    for search in searches:
        hits, ref, searched, rejected = run_search(search)

        key = search.name
        previous_best = state.get(key, {}).get("best_price")

        if not hits and not search.notify_when_empty:
            print(f"  (no results, notify_when_empty=False - skipping notification)")
            continue

        message = format_search_message(
            search_name=search.name,
            hits=hits,
            ref=ref,
            w=search.weights,
            top_n=search.top_n,
            previous_best=previous_best,
            searched_count=searched,
            rejected_count=rejected,
        )

        print("\n" + "-" * 60)
        print(message)
        print("-" * 60)

        if not args.dry_run:
            send_telegram(message)

        if hits:
            state[key] = {
                "best_price": hits[0].metrics.price,
                "updated": date.today().isoformat(),
            }

    if not args.dry_run:
        save_state(state)


if __name__ == "__main__":
    main()
