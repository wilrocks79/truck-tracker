# Squamish Truck Tracker

Tracks used truck inventory across 3 dealerships in Squamish, BC. Scrapes daily, detects price changes, flags sold vehicles, and serves a live dashboard.

**[Live Dashboard](https://wilrocks79.github.io/truck-tracker/dashboard.html)**

## Dealers

| Dealer | Platform | Status |
|--------|----------|--------|
| [Squamish Toyota](https://www.squamishtoyota.com/inventory/used/) | eDealer | Working |
| [Greg Gardner Motors](https://www.greggardnergm.com/inventory/used/) | eDealer | Working |
| [Coastal Ford Squamish](https://www.coastalfordsquamish.com/en/used-inventory) | SM360 (GraphQL) | Working |

## What It Tracks

- **New listings** — trucks that appear for the first time
- **Price changes** — price drops and increases with full history
- **Sold / off market** — trucks that disappear from a dealer's site
- **Returned** — trucks that reappear after being removed
- **MPG data** — fetched from the [fueleconomy.gov](https://www.fueleconomy.gov/) EPA API

## Dashboard Features

- Thumbnail images for each listing
- Filter by dealer, make, and price range
- Sort by price, year, mileage, or days on market
- Toggle between miles and kilometres (MPG ↔ L/100km)
- Sold/off market section with greyed-out cards
- Full price history log

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper
python run_scraper.py

# Run with verbose logging
python run_scraper.py --verbose

# Scrape a single dealer
python run_scraper.py --dealer coastal_ford

# Open the dashboard
open data/dashboard.html

# Or generate and open in one step
python generate_dashboard.py --open
```

## Automation

The scraper runs daily at 8am Pacific via GitHub Actions. It scrapes all dealers, commits updated data, and deploys the dashboard to GitHub Pages.

To trigger a manual run:
```bash
gh workflow run scrape.yml
```

## Project Structure

```
├── run_scraper.py          # Main entry point
├── scrapers.py             # Dealer-specific scrapers (eDealer, SM360)
├── tracker.py              # Change detection and inventory management
├── fuel_economy.py         # EPA MPG lookup and caching
├── config.py               # Dealer configs, truck filters, settings
├── dashboard.html          # Dashboard template
├── generate_dashboard.py   # Injects data into dashboard template
├── data/
│   ├── inventory.csv       # Current inventory (all vehicles ever seen)
│   ├── price_history.csv   # Log of all price events
│   ├── mpg_cache.json      # Cached EPA MPG lookups
│   └── dashboard.html      # Generated dashboard (deployed to Pages)
└── .github/workflows/
    └── scrape.yml          # Daily scrape + deploy workflow
```

## Adding a Dealer

Add a new entry to `DEALERS` in `config.py`. The scraper supports two platforms:

- **eDealer** — HTML scraping with pagination (`platform: "edealer"`)
- **SM360** — GraphQL API (`platform: "sm360"`)
