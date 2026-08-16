"""
notify.py

Formatting + sending to Telegram. Messages use HTML formatting,
which Telegram supports directly in sendMessage.
"""

from __future__ import annotations

import html
import os
from datetime import date

import requests

from models import TripMetrics
from scoring import MarketReference, Weights, effective_cost, explain

TELEGRAM_API = "https://api.telegram.org"

# We format weekdays ourselves instead of using strftime('%a'), because that
# would give names in the server's locale - and GitHub Actions doesn't have
# Norwegian locale installed. Change this list to your language.
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.strftime('%d.%m')}"


class Hit:
    """A trip that passed the filters, with context about when it departs."""

    def __init__(
        self,
        metrics: TripMetrics,
        out_date: date,
        home_date: date,
        origin: str,
        destination: str,
    ):
        self.metrics = metrics
        self.out_date = out_date
        self.home_date = home_date
        self.origin = origin
        self.destination = destination

    @property
    def nights(self) -> int:
        return (self.home_date - self.out_date).days


def format_hit(
    rank: int, hit: Hit, ref: MarketReference, w: Weights, previous_best: float | None
) -> str:
    m = hit.metrics
    cost = effective_cost(m, ref, w)

    stops_txt = "direct" if m.stops == 0 else f"{m.stops} stops"

    line1 = (
        f"<b>{rank}. {m.price:.0f}</b> · {stops_txt} · "
        f"{m.total_hours:.1f}h · {hit.nights} nights"
    )
    line2 = (
        f"   {fmt_date(hit.out_date)} → {fmt_date(hit.home_date)} · "
        f"{html.escape(m.route)} · {html.escape(', '.join(m.airlines))}"
    )
    line3 = f"   <i>weighted: {cost:.0f}</i> — {html.escape(explain(m, ref, w))}"

    lines = [line1, line2, line3]

    # Add booking link if available
    if m.booking_url:
        line4 = f"   <a href='{html.escape(m.booking_url)}'>✈️ Book on Google Flights</a>"
        lines.append(line4)

    if rank == 1 and previous_best is not None:
        delta = m.price - previous_best
        if abs(delta) >= 50:
            arrow = "📉" if delta < 0 else "📈"
            lines.append(f"   {arrow} {delta:+.0f} since last run")

    return "\n".join(lines)


def format_search_message(
    search_name: str,
    hits: list[Hit],
    ref: MarketReference,
    w: Weights,
    top_n: int,
    previous_best: float | None,
    searched_count: int,
    rejected_count: int,
) -> str:
    header = f"✈️ <b>{html.escape(search_name)}</b>"

    if not hits:
        return (
            f"{header}\n\nNo results passed filters today "
            f"({searched_count} date combinations checked, "
            f"{rejected_count} trips rejected)."
        )

    body = "\n\n".join(
        format_hit(i, hit, ref, w, previous_best)
        for i, hit in enumerate(hits[:top_n], start=1)
    )
    footer = (
        f"\n\n<i>Fastest on route now: {ref.fastest_hours:.1f}h · "
        f"typical price: {ref.typical_price:.0f} · "
        f"{searched_count} date combinations checked</i>"
    )
    return f"{header}\n\n{body}{footer}"


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
