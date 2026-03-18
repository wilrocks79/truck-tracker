#!/usr/bin/env python3
"""
Squamish Used Truck Inventory Tracker
======================================
Scrapes used truck inventory from three Squamish, BC dealerships:
  - Squamish Toyota
  - Greg Gardner Motors (GM/Chevrolet/Buick/GMC)
  - Coastal Ford Squamish

Tracks new listings, removed listings, and price changes over time.

Usage:
    python run_scraper.py              # Scrape trucks only (default)
    python run_scraper.py --all        # Scrape ALL used vehicles, not just trucks
    python run_scraper.py --dealer squamish_toyota   # Scrape one dealer only
    python run_scraper.py --verbose    # Show debug logging
"""

import argparse
import logging
import sys
import os
from datetime import datetime

# Ensure we run from the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import DEALERS, DATA_DIR, LOG_FILE, INVENTORY_CSV
from scrapers import scrape_edealer, scrape_sm360, Vehicle
from tracker import update_inventory, ensure_data_dir


def setup_logging(verbose: bool = False):
    """Configure logging to both file and console."""
    ensure_data_dir()
    level = logging.DEBUG if verbose else logging.INFO

    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))

    logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])


def scrape_dealer(dealer_key: str, dealer_config: dict) -> list[Vehicle]:
    """Dispatch to the appropriate scraper based on platform."""
    platform = dealer_config["platform"]
    if platform == "edealer":
        return scrape_edealer(dealer_config)
    elif platform == "sm360":
        return scrape_sm360(dealer_config)
    else:
        logging.error(f"Unknown platform '{platform}' for {dealer_key}")
        return []


def print_summary(summary: dict):
    """Print a human-readable summary of changes."""
    print("\n" + "=" * 60)
    print(f"  SCRAPE SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print(f"\n  Active trucks: {summary['total_active']}")
    print(f"  Total tracked (all time): {summary['total_tracked']}")

    if summary["new_listings"]:
        print(f"\n  NEW LISTINGS ({len(summary['new_listings'])}):")
        for v in summary["new_listings"]:
            print(f"    + {v['year']} {v['make']} {v['model']} — {v['price']} ({v['dealer']})")

    if summary["price_changes"]:
        print(f"\n  PRICE CHANGES ({len(summary['price_changes'])}):")
        for v in summary["price_changes"]:
            old_num = int("".join(c for c in v["old_price"] if c.isdigit()) or "0")
            new_num = int("".join(c for c in v["new_price"] if c.isdigit()) or "0")
            direction = "↓" if new_num < old_num else "↑"
            print(f"    {direction} {v['year']} {v['make']} {v['model']} — {v['old_price']} → {v['new_price']} ({v['dealer']})")

    if summary["removed"]:
        print(f"\n  REMOVED ({len(summary['removed'])}):")
        for v in summary["removed"]:
            print(f"    - {v['year']} {v['make']} {v['model']} ({v['dealer']})")

    if not summary["new_listings"] and not summary["price_changes"] and not summary["removed"]:
        print("\n  No changes since last run.")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Squamish Used Truck Inventory Tracker"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Track ALL used vehicles, not just trucks"
    )
    parser.add_argument(
        "--dealer", type=str, choices=list(DEALERS.keys()),
        help="Scrape only a specific dealer"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose/debug logging"
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Starting Squamish truck inventory scrape")
    start = datetime.now()

    # Determine which dealers to scrape
    if args.dealer:
        dealers_to_scrape = {args.dealer: DEALERS[args.dealer]}
    else:
        dealers_to_scrape = DEALERS

    # Scrape all dealers
    all_vehicles: list[Vehicle] = []
    for key, config in dealers_to_scrape.items():
        try:
            vehicles = scrape_dealer(key, config)
            all_vehicles.extend(vehicles)
            logger.info(f"  {config['name']}: {len(vehicles)} vehicles scraped")
        except Exception as e:
            logger.error(f"  Failed to scrape {config['name']}: {e}", exc_info=True)

    trucks_only = not args.all
    mode = "all vehicles" if args.all else "trucks only"
    logger.info(f"Total scraped: {len(all_vehicles)} vehicles (filtering: {mode})")

    if trucks_only:
        truck_count = sum(1 for v in all_vehicles if v.is_truck())
        logger.info(f"  Of which {truck_count} are identified as trucks")

    # Update inventory and get changes
    summary = update_inventory(all_vehicles, trucks_only=trucks_only)

    # Print summary
    print_summary(summary)

    # Enrich with MPG data from fueleconomy.gov
    try:
        from fuel_economy import enrich_inventory_with_mpg
        enrich_inventory_with_mpg(INVENTORY_CSV)
    except Exception as e:
        logger.warning(f"MPG enrichment failed: {e}")

    # Regenerate the dashboard with fresh data
    try:
        from generate_dashboard import generate
        generate()
    except Exception as e:
        logger.warning(f"Dashboard generation failed: {e}")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"Scrape completed in {elapsed:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
