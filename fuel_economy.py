"""
Fetch MPG data from fueleconomy.gov (US EPA).

Free API, no key required. We fuzzy-match year/make/model from our inventory
against the EPA database and cache results to avoid repeat lookups.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional

import requests

from config import DATA_DIR, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Cache file — stores year/make/model -> MPG so we don't re-query
MPG_CACHE_FILE = os.path.join(DATA_DIR, "mpg_cache.json")

BASE_URL = "https://www.fueleconomy.gov/ws/rest/vehicle"


def _load_cache() -> dict:
    if os.path.exists(MPG_CACHE_FILE):
        with open(MPG_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MPG_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _cache_key(year: str, make: str, model: str) -> str:
    return f"{year}|{make}|{model}".lower().strip()


def _get_xml(url: str) -> Optional[ET.Element]:
    """Fetch XML from fueleconomy.gov."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return ET.fromstring(resp.text)
    except Exception as e:
        logger.debug(f"  MPG API error: {e}")
        return None


def _find_best_model(year: str, make: str, model: str, fuel_type: str = "") -> Optional[str]:
    """
    Find the best matching EPA model name for a given year/make/model.

    EPA model names include drivetrain (e.g. "Silverado 1500 4WD"),
    so we fuzzy-match. Our scraped models often include trim info
    (e.g. "Silverado 1500 RST") which the EPA doesn't use — so we
    progressively strip words from the right until we get a hit.
    """
    root = _get_xml(f"{BASE_URL}/menu/model?year={year}&make={make}")
    if root is None:
        return None

    items = root.findall("menuItem")
    if not items:
        return None

    epa_names = []
    for item in items:
        text_el = item.find("text")
        if text_el is not None and text_el.text:
            epa_names.append(text_el.text)

    # Build a list of model name variants to try, stripping trim words
    # e.g. "Silverado 1500 RST" -> try "Silverado 1500 RST", "Silverado 1500", "Silverado"
    model_clean = model.strip()
    # Strip drivetrain words that won't appear in EPA base name
    model_clean = re.sub(r'\b(2wd|4wd|4x4|awd|fwd|rwd)\b', '', model_clean, flags=re.IGNORECASE).strip()

    words = model_clean.split()
    search_terms = []
    for i in range(len(words), 0, -1):
        search_terms.append(" ".join(words[:i]).lower())

    is_diesel = "diesel" in fuel_type.lower() if fuel_type else False
    is_electric = "electric" in fuel_type.lower() if fuel_type else False

    for term in search_terms:
        # Normalize hyphens — EPA uses "F150" but dealers use "F-150"
        term_nohyphen = term.replace("-", "")
        candidates = []
        for epa_name in epa_names:
            epa_lower = epa_name.lower()
            epa_nohyphen = epa_lower.replace("-", "")
            if term in epa_lower or term_nohyphen in epa_nohyphen:
                # Score: prefer 4WD, prefer matching fuel type, deprioritize electric
                score = 0
                if "4wd" in epa_lower or "4x4" in epa_lower:
                    score += 10
                elif "awd" in epa_lower:
                    score += 8
                elif "2wd" in epa_lower:
                    score += 5

                # Avoid electric matches for gas trucks and vice versa
                is_epa_electric = "elec" in epa_lower or "ev" in epa_lower or "lightning" in epa_lower
                if is_electric and is_epa_electric:
                    score += 20
                elif not is_electric and is_epa_electric:
                    score -= 50  # Strong penalty — don't match Lightning for gas F-150
                elif is_diesel and "diesel" in epa_lower:
                    score += 15

                candidates.append((score, epa_name))

        if candidates:
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]

    return None


def _get_vehicle_mpg(year: str, make: str, epa_model: str) -> Optional[dict]:
    """Get MPG for a specific year/make/EPA model. Returns the first option's data."""
    root = _get_xml(
        f"{BASE_URL}/menu/options?year={year}&make={make}&model={epa_model}"
    )
    if root is None:
        return None

    items = root.findall("menuItem")
    if not items:
        return None

    # Take the first option (most common engine/trim)
    vehicle_id = items[0].find("value").text
    if not vehicle_id:
        return None

    # Fetch full vehicle data
    vroot = _get_xml(f"{BASE_URL}/{vehicle_id}")
    if vroot is None:
        return None

    def get_field(name):
        el = vroot.find(name)
        return el.text if el is not None else ""

    return {
        "mpg_city": get_field("city08"),
        "mpg_highway": get_field("highway08"),
        "mpg_combined": get_field("comb08"),
        "fuel_type_epa": get_field("fuelType"),
    }


def lookup_mpg(year: str, make: str, model: str, fuel_type: str = "") -> dict:
    """
    Look up MPG for a vehicle. Returns dict with mpg_city, mpg_highway, mpg_combined.
    Uses cache to avoid repeat API calls.
    """
    if not year or not make or not model:
        return {}

    cache = _load_cache()
    key = _cache_key(year, make, model)

    if key in cache:
        return cache[key]

    logger.info(f"  Looking up MPG for {year} {make} {model}...")

    # Find the EPA model name
    epa_model = _find_best_model(year, make, model, fuel_type)
    if not epa_model:
        logger.debug(f"    No EPA model match for {make} {model}")
        cache[key] = {}
        _save_cache(cache)
        return {}

    logger.debug(f"    Matched EPA model: {epa_model}")

    # Get MPG data
    mpg = _get_vehicle_mpg(year, make, epa_model)
    if not mpg:
        logger.debug(f"    No MPG data for {epa_model}")
        cache[key] = {}
        _save_cache(cache)
        return {}

    logger.info(
        f"    {year} {make} {model} → "
        f"{mpg['mpg_city']} city / {mpg['mpg_highway']} hwy / {mpg['mpg_combined']} combined"
    )
    cache[key] = mpg
    _save_cache(cache)
    return mpg


def enrich_inventory_with_mpg(inventory_csv: str):
    """Add MPG data to existing inventory CSV records."""
    if not os.path.exists(inventory_csv):
        return

    # Read existing inventory
    rows = []
    with open(inventory_csv, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    # Add MPG fields if not present
    mpg_fields = ["mpg_city", "mpg_highway", "mpg_combined"]
    new_fields = [f for f in mpg_fields if f not in fieldnames]
    fieldnames = fieldnames + new_fields

    updated = 0
    for row in rows:
        # Skip if already has MPG data
        if row.get("mpg_combined"):
            continue

        mpg = lookup_mpg(row.get("year", ""), row.get("make", ""), row.get("model", ""), row.get("fuel_type", ""))
        if mpg:
            for field in mpg_fields:
                row[field] = mpg.get(field, "")
            updated += 1

    if updated:
        with open(inventory_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Added MPG data to {updated} vehicles")
    else:
        logger.info("All vehicles already have MPG data (or no matches found)")
