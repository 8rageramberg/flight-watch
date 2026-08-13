# Flight Watch

Automatic flight price monitor for cheap weekend getaways. Checks Lisbon flights every Monday morning, ranks deals by value, and sends the best options to Telegram. Built with SerpApi, GitHub Actions, and Python.

## What It Does

- **Searches** Lisbon flights (or any destination) for weekend trips
- **Ranks** results using weighted scoring logic (price + duration penalties)
- **Sends** top deals to Telegram with direct Google Flights booking links
- **Runs** automatically every Monday at 6 AM CET via GitHub Actions
- **Costs** ~$2-3/month (SerpApi only; GitHub Actions is free)

## Quick Start

### 1. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the API token you receive

### 2. Get your Telegram chat ID

1. Message your new bot
2. Open: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find your `"chat":{"id":XXXXX}`

### 3. Get a SerpApi account

1. Go to https://serpapi.com/
2. Sign up (free trial: 100 searches)
3. Copy your API key

### 4. Add secrets to GitHub

Go to: Settings → Secrets and variables → Actions → New repository secret

Add three secrets:
- `TELEGRAM_BOT_TOKEN` = your bot token
- `TELEGRAM_CHAT_ID` = your chat ID  
- `SERPAPI_API_KEY` = your SerpApi key

### 5. Done

Workflow runs automatically every Monday at 6 AM CET. You'll get a Telegram message with cheap flights.

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Test the ranking logic (no API calls)
python test_scoring.py

# Dry run (searches but doesn't send Telegram)
python flight_watch.py --dry-run

# Run and send to Telegram
python flight_watch.py
```

## Configuration

Edit `config.py` to customize:

```python
Search(
    name="Lisbon – Weekend Getaways",
    origins=["OSL"],
    destinations=["LIS"],
    window=DateWindow(
        start=date(2026, 9, 18),
        end=date(2026, 10, 12),
        trip_lengths=[2, 3],           # nights away
        step_days=7,                   # check weekly
        weekdays=[3, 4, 5],            # Thu/Fri/Sat only
    ),
    limits=EUROPE_LIMITS,              # filter rules
    weights=DEFAULT_WEIGHTS,           # scoring weights
)
```

### Add more destinations

Copy the Lisbon search block and change `destinations=["CDG"]` (Paris), `["BCN"]` (Barcelona), etc.

## How Ranking Works

### Stage 1: Hard Filters
Trips that violate rules are rejected entirely:
- Max price cap
- Max stops (2)
- Minimum layover time (realistic connections only)
- Duration + price combos (e.g., "if 10+ hours, must cost under 3500")

### Stage 2: Soft Scoring
Surviving trips are ranked by "weighted cost" = actual price + penalties:

| Issue | Penalty |
| --- | --- |
| Each hour longer than fastest | 110 |
| 1 stop / 2 stops / 3+ stops | 300 / 1100 / 2600 |
| Connection under 1.25 hours | 450 |
| Long layover (each hour over 3h) | 130 |
| Overnight layover (7+ hours) | +700 |
| Early departure (before 7 AM) | 350 |
| Late arrival (after 11 PM) | 350 |

### Bargain Discount
When price is under 55% of typical route price, penalties halve. Lets cheap 2-stop flights beat expensive direct flights.

### Reference Points
"Fastest" and "typical price" are calculated fresh from each week's results, not hardcoded. So the same logic works for 4-hour European trips and 15-hour long-hauls.

## Architecture

```
GitHub Actions (weekly trigger)
    ↓
flight_watch.py (orchestration)
    ↓
query_one() (SerpApi → Google Flights)
    ↓
compute_metrics() (parse flight data)
    ↓
scoring.py (rank by weighted cost)
    ↓
notify.py (Telegram + Google Flights links)
```

## Costs

- **SerpApi:** ~$2-3/month (32 searches/month for 1 weekly Lisbon search)
- **GitHub Actions:** Free (well under quota)
- **Telegram:** Free

## Known Limitations

- **SerpApi free trial:** 100 searches. After that, you pay per search (~$0.01-0.02).
- **One search per week:** Tune `DateWindow` and `step_days` to search more/less frequently.
- **Round-trip metrics describe outbound only:** Price is full round-trip but time/stops/airlines shown are for outbound leg. Return might differ.
- **No historical price tracking yet:** Just best price from current search. `state.json` stores this for next run.

## Tuning the Filters

Test filter changes locally without API calls:

```bash
python test_scoring.py
```

This runs the scoring logic against fictional (but realistic) test flights. Edit `EUROPE_LIMITS` or `DEFAULT_WEIGHTS` in `config.py`, then re-run to see effects immediately.

## Manual Workflow Trigger

To test without waiting for Monday:

1. Go to Actions tab on GitHub
2. Select "Flight Watch" workflow  
3. Click "Run workflow"
4. Select main branch → "Run workflow"

Should complete in ~2 minutes and send a Telegram message.

## File Structure

| File | Purpose |
| --- | --- |
| `config.py` | Search definitions, filter rules, scoring weights |
| `flight_watch.py` | Main orchestration script |
| `models.py` | Data structures, SerpApi response parsing |
| `scoring.py` | Hard filters + soft ranking logic |
| `notify.py` | Telegram formatting and sending |
| `test_scoring.py` | Test harness (fictional flights, no API calls) |
| `.github/workflows/flight-watch.yml` | GitHub Actions schedule |

## Future Ideas

- Store price history (cheapest price per route over time)
- Alert if price drops from previous week
- Support multiple destinations simultaneously
- Email notifications
- Price prediction / "when to book" advice
- Integration with flight booking APIs

## License

MIT
