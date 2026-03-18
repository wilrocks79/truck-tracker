"""
Inventory tracker — manages data storage, change detection, and price history.
"""

import csv
import os
import logging
from datetime import datetime
from dataclasses import asdict, fields

from scrapers import Vehicle
from config import DATA_DIR, INVENTORY_CSV, HISTORY_CSV

logger = logging.getLogger(__name__)


def _price_to_cents(price_str: str) -> int:
    """Convert a price string like '$56988' to an integer. Returns 0 if unparseable."""
    if not price_str:
        return 0
    digits = "".join(c for c in price_str if c.isdigit())
    return int(digits) if digits else 0

INVENTORY_FIELDS = [
    "dealer", "year", "make", "model", "trim", "price", "mileage",
    "vin", "stock_number", "body_type", "drivetrain", "transmission",
    "fuel_type", "colour", "url", "image_url", "date_first_seen",
    "date_last_seen", "current_price", "is_active",
    "mpg_city", "mpg_highway", "mpg_combined",
]

HISTORY_FIELDS = ["vin", "dealer", "date", "old_price", "new_price", "event"]


def ensure_data_dir():
    """Create the data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_inventory() -> dict[str, dict]:
    """Load existing inventory from CSV. Returns dict keyed by VIN."""
    ensure_data_dir()
    inventory = {}
    if not os.path.exists(INVENTORY_CSV):
        return inventory

    with open(INVENTORY_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vin = row.get("vin", "")
            if vin:
                inventory[vin] = row

    logger.info(f"Loaded {len(inventory)} existing inventory records")
    return inventory


def save_inventory(inventory: dict[str, dict]):
    """Save inventory dict to CSV."""
    ensure_data_dir()
    if not inventory:
        return

    with open(INVENTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in inventory.values():
            writer.writerow(row)

    logger.info(f"Saved {len(inventory)} inventory records")


def append_history(events: list[dict]):
    """Append price history events to the history CSV."""
    ensure_data_dir()
    file_exists = os.path.exists(HISTORY_CSV)

    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for event in events:
            writer.writerow(event)


def update_inventory(scraped_vehicles: list[Vehicle], trucks_only: bool = True) -> dict:
    """
    Update inventory with newly scraped vehicles.
    Returns a summary of changes.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    existing = load_inventory()
    history_events = []

    new_listings = []
    price_changes = []
    returned_listings = []  # Were inactive, now active again
    still_active = set()

    for v in scraped_vehicles:
        if trucks_only and not v.is_truck():
            continue

        if not v.vin:
            continue

        still_active.add(v.vin)

        if v.vin in existing:
            record = existing[v.vin]
            was_inactive = record.get("is_active") == "false"

            record["date_last_seen"] = today
            record["is_active"] = "true"

            # Update mutable fields
            if v.url:
                record["url"] = v.url
            if v.image_url:
                record["image_url"] = v.image_url

            # Check for price change (compare as numbers, not strings)
            old_price = record.get("current_price", "")
            new_price = v.price
            old_cents = _price_to_cents(old_price)
            new_cents = _price_to_cents(new_price)
            if old_cents and new_cents and old_cents != new_cents:
                price_changes.append({
                    "vin": v.vin,
                    "dealer": v.dealer,
                    "year": v.year,
                    "make": v.make,
                    "model": v.model,
                    "old_price": old_price,
                    "new_price": new_price,
                })
                history_events.append({
                    "vin": v.vin,
                    "dealer": v.dealer,
                    "date": today,
                    "old_price": old_price,
                    "new_price": new_price,
                    "event": "price_change",
                })
                record["current_price"] = new_price

            # Check if it was previously inactive (re-appeared)
            if was_inactive:
                returned_listings.append(v.vin)
                history_events.append({
                    "vin": v.vin,
                    "dealer": v.dealer,
                    "date": today,
                    "old_price": "",
                    "new_price": v.price,
                    "event": "returned",
                })

        else:
            # New listing
            record = {
                "dealer": v.dealer,
                "year": v.year,
                "make": v.make,
                "model": v.model,
                "trim": v.trim,
                "price": v.price,
                "mileage": v.mileage,
                "vin": v.vin,
                "stock_number": v.stock_number,
                "body_type": v.body_type,
                "drivetrain": v.drivetrain,
                "transmission": v.transmission,
                "fuel_type": v.fuel_type,
                "colour": v.colour,
                "url": v.url,
                "image_url": v.image_url,
                "date_first_seen": today,
                "date_last_seen": today,
                "current_price": v.price,
                "is_active": "true",
            }
            existing[v.vin] = record
            new_listings.append({
                "vin": v.vin,
                "dealer": v.dealer,
                "year": v.year,
                "make": v.make,
                "model": v.model,
                "price": v.price,
            })
            history_events.append({
                "vin": v.vin,
                "dealer": v.dealer,
                "date": today,
                "old_price": "",
                "new_price": v.price,
                "event": "new_listing",
            })

    # Mark vehicles not seen in this scrape as inactive
    removed = []
    for vin, record in existing.items():
        if vin not in still_active and record.get("is_active") == "true":
            # Only mark as removed if the dealer was scraped this run
            scraped_dealers = {v.dealer for v in scraped_vehicles}
            if record.get("dealer") in scraped_dealers:
                record["is_active"] = "false"
                removed.append({
                    "vin": vin,
                    "dealer": record.get("dealer", ""),
                    "year": record.get("year", ""),
                    "make": record.get("make", ""),
                    "model": record.get("model", ""),
                })
                history_events.append({
                    "vin": vin,
                    "dealer": record.get("dealer", ""),
                    "date": today,
                    "old_price": record.get("current_price", ""),
                    "new_price": "",
                    "event": "removed",
                })

    # Save
    save_inventory(existing)
    if history_events:
        append_history(history_events)

    return {
        "new_listings": new_listings,
        "price_changes": price_changes,
        "removed": removed,
        "returned": returned_listings,
        "total_active": sum(1 for r in existing.values() if r.get("is_active") == "true"),
        "total_tracked": len(existing),
    }
