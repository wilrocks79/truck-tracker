"""
Scrapers for each dealer platform.
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from config import REQUEST_HEADERS, REQUEST_TIMEOUT, TRUCK_MODELS, TRUCK_BODY_TYPES

logger = logging.getLogger(__name__)


@dataclass
class Vehicle:
    dealer: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    trim: str = ""
    price: str = ""
    mileage: str = ""
    vin: str = ""
    stock_number: str = ""
    body_type: str = ""
    drivetrain: str = ""
    transmission: str = ""
    fuel_type: str = ""
    colour: str = ""
    url: str = ""
    image_url: str = ""

    def is_truck(self) -> bool:
        """Check if this vehicle is a truck based on body type or model name."""
        searchable = f"{self.body_type} {self.model} {self.trim}".lower()
        for truck_type in TRUCK_BODY_TYPES:
            if truck_type in searchable:
                return True
        for truck_model in TRUCK_MODELS:
            if truck_model in searchable:
                return True
        return False


def _get_page(url: str) -> Optional[BeautifulSoup]:
    """Fetch a page and return a BeautifulSoup object."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def _clean_price(text: str) -> str:
    """Extract a numeric price from text like '$17,988' or '*$26,400'."""
    match = re.search(r"\$[\d,]+", text)
    if match:
        return match.group(0).replace(",", "")
    return ""


def _clean_mileage(text: str) -> str:
    """Extract mileage from text like '106,612 km' or '106,612 KM'."""
    match = re.search(r"([\d,]+)\s*km", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "")
    return ""


# ---------------------------------------------------------------------------
# eDealer platform scraper (Squamish Toyota, Greg Gardner GM)
# ---------------------------------------------------------------------------

def _parse_edealer_card(card, dealer_name: str, base_url: str) -> Optional[Vehicle]:
    """Parse a single vehicle card from the eDealer platform."""
    text = card.get_text(separator="\n", strip=True)
    if not text or len(text) < 20:
        return None  # Skip skeleton/empty cards

    v = Vehicle(dealer=dealer_name)

    # URL from the title/image link
    title_link = card.select_one('a[href*="/inventory/"]')
    if title_link:
        href = title_link.get("href", "")
        v.url = href if href.startswith("http") else base_url + href

    # Thumbnail image
    img = card.select_one('img[src*="media.getedealer.com"]')
    if img:
        v.image_url = img.get("src", "")

    # Year, Make, Model from the card text (title link often wraps an image, not text)
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        year_match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", line)
        if year_match:
            v.year = year_match.group(1)
            v.make = year_match.group(2)
            v.model = year_match.group(3)
            break

    # Trim - often on the line after the title
    trim_el = card.select_one(".vehicle-card-trim, .trim")
    if trim_el:
        v.trim = trim_el.get_text(strip=True)

    # VIN
    vin_match = re.search(r"VIN:\s*(\w{17})", text)
    if vin_match:
        v.vin = vin_match.group(1)

    # Stock number
    stock_match = re.search(r"Stock\s*#?\s*:?\s*(\w+)", text, re.IGNORECASE)
    if not stock_match:
        stock_match = re.search(r"\b([A-Z]\d{5,6})\b", text)
    if stock_match:
        v.stock_number = stock_match.group(1)

    # Price
    v.price = _clean_price(text)

    # Mileage
    v.mileage = _clean_mileage(text)

    # Body type, drivetrain, etc. from attribute tags
    lines = text.split("\n")
    for line in lines:
        line_lower = line.strip().lower()
        if line_lower in ("suv", "sedan", "hatchback", "truck", "van", "coupe", "wagon", "convertible", "minivan"):
            v.body_type = line.strip()
        if line_lower in ("awd", "fwd", "rwd", "4wd", "4x4", "4x2", "2wd", "all wheel drive", "front wheel drive"):
            v.drivetrain = line.strip()
        if line_lower in ("automatic", "manual", "cvt"):
            v.transmission = line.strip()
        if line_lower in ("gasoline", "diesel", "electric", "hybrid", "plug-in hybrid", "flex fuel"):
            v.fuel_type = line.strip()
        # Colour - check for known colour words
        if re.match(r"^(black|white|grey|gray|silver|red|blue|green|brown|beige|gold|orange|yellow|maroon|burgundy|tan|pearl|bronze|charcoal|graphite|cement|lunar|magnetic|midnight|army|ice|oxford|shadow|super|rapid|cactus|dark|agate|carbonized|antimatter|area|alto|avalanche).*$", line_lower) and len(line.strip()) < 30:
            v.colour = line.strip()

    # Parse trim from the text if not found via selector
    if not v.trim and v.model:
        # Try to get the line after year/make/model title
        for i, line in enumerate(lines):
            if v.model in line and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                # Trim is usually short and doesn't look like other fields
                if candidate and len(candidate) < 60 and not re.match(r"^(VIN|Stock|\$|[\d,]+\s*km)", candidate, re.IGNORECASE):
                    v.trim = candidate
                break

    return v


def scrape_edealer(dealer_config: dict) -> list[Vehicle]:
    """Scrape all used vehicles from an eDealer platform dealer, handling pagination."""
    dealer_name = dealer_config["name"]
    base_url = dealer_config["base_url"]
    inventory_url = dealer_config["inventory_url"]

    all_vehicles = []
    page = 1
    max_pages = 10  # Safety limit

    while page <= max_pages:
        page_url = inventory_url if page == 1 else f"{inventory_url}?page={page}"
        logger.info(f"Scraping {dealer_name} page {page} from {page_url}")
        soup = _get_page(page_url)
        if not soup:
            break

        cards = soup.select(".cell.card.js-inventory-item-id")
        logger.info(f"  Found {len(cards)} vehicle cards on page {page}")

        if not cards:
            break  # No more pages

        page_vehicles = []
        for card in cards:
            v = _parse_edealer_card(card, dealer_name, base_url)
            if v and v.vin:
                page_vehicles.append(v)

        logger.info(f"  Parsed {len(page_vehicles)} vehicles with VINs on page {page}")

        if not page_vehicles:
            break  # No valid vehicles on this page

        all_vehicles.extend(page_vehicles)

        # Check if there's a next page link
        next_link = soup.select_one(f'a[href*="page={page + 1}"]')
        if not next_link:
            break

        page += 1

    logger.info(f"  Total: {len(all_vehicles)} vehicles across {page} page(s)")
    return all_vehicles


# ---------------------------------------------------------------------------
# SM360 platform scraper (Coastal Ford Squamish)
# ---------------------------------------------------------------------------

def _parse_sm360_tile(tile, dealer_name: str, base_url: str) -> Optional[Vehicle]:
    """Parse a single vehicle tile from the SM360 platform HTML."""
    text = tile.get_text(separator="\n", strip=True)
    if not text or len(text) < 20:
        return None

    v = Vehicle(dealer=dealer_name)

    lines = text.split("\n")

    # Stock number (e.g. #14U1284)
    stock_match = re.search(r"#(\w+)", text)
    if stock_match:
        v.stock_number = stock_match.group(1)

    # VIN
    vin_match = re.search(r"VIN\s+(\w{17})", text)
    if vin_match:
        v.vin = vin_match.group(1)

    # Year, Make, Model (e.g. "2023 Ford Bronco Sport")
    # Use a specific year range to avoid matching stock numbers; make is a single word
    year_match = re.search(r"((?:19|20)\d{2})\s+([A-Z][a-zA-Z]+)\s+(.+?)(?:\n|$)", text)
    if year_match:
        v.year = year_match.group(1)
        v.make = year_match.group(2)
        v.model = year_match.group(3).strip()

    # Trim - typically the line after the year/make/model
    for i, line in enumerate(lines):
        if v.year and v.make and v.year in line and v.make in line:
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and not candidate.startswith(("VIN", "#", "$")) and len(candidate) < 80:
                    v.trim = candidate
            break

    # Price - look for the selling price (the asterisked one is usually the final price)
    prices = re.findall(r"\*?\$[\d,]+", text)
    if prices:
        # Take the last price which is usually the sale/final price
        v.price = _clean_price(prices[-1])

    # Mileage
    v.mileage = _clean_mileage(text)

    # Drivetrain, transmission
    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()
        if line_lower in ("4x4", "4x2", "awd", "fwd", "rwd", "all wheel drive", "front wheel drive", "rear wheel drive"):
            v.drivetrain = line_clean
        if line_lower in ("automatic", "manual", "cvt"):
            v.transmission = line_clean

    # Build URL from stock number
    if v.stock_number:
        v.url = f"{base_url}/en/used-inventory"  # SM360 doesn't have clean detail URLs easily

    return v


def scrape_sm360(dealer_config: dict) -> list[Vehicle]:
    """Scrape all used vehicles from an SM360 platform dealer."""
    dealer_name = dealer_config["name"]
    base_url = dealer_config["base_url"]
    inventory_url = dealer_config["inventory_url"]

    logger.info(f"Scraping {dealer_name} from {inventory_url}")

    # First try the GraphQL API (SM360 v2 uses this)
    vehicles = _scrape_sm360_graphql(dealer_config)
    if vehicles:
        return vehicles

    # Then try the REST API
    vehicles = _scrape_sm360_api(dealer_config)
    if vehicles:
        return vehicles

    # Fallback to HTML parsing (limited — SM360 is JS-rendered)
    logger.info(f"  API methods failed, falling back to HTML parsing")
    return _scrape_sm360_html(dealer_config)


def _scrape_sm360_graphql(dealer_config: dict) -> list[Vehicle]:
    """Scrape SM360 via the GraphQL searchVehicles query."""
    dealer_name = dealer_config["name"]
    graphql_url = dealer_config.get("graphql_url")
    api_params = dealer_config.get("api_params", {})

    if not graphql_url:
        return []

    org_unit_id = api_params.get("organizationUnitId", "")
    if not org_unit_id:
        return []

    # The SM360 GraphQL schema uses searchVehicles (not "inventory").
    # Variables don't work reliably with this endpoint — use inline args.
    # VDP URL template for building detail page links.
    vdp_template = dealer_config.get(
        "vdp_url",
        "/en/used-inventory/{make}/{model}/{year}/{year}-{make}-{model}-id{vehicleId}",
    )

    query = (
        "{ searchVehicles("
        f"first: 100, organizationUnitId: {int(org_unit_id)}, "
        'vehicleCriteria: { colanderSlug: "used" }, '
        "pageRequest: { pageNumber: 0, pageSize: 100 }"
        ") { totalCount nodes { "
        "id vin stockNo year sold odometer "
        "make { name } model { name } trim { name } "
        "prices { sale regular } "
        "multimedia { mainPicture { url } } "
        "characteristics { "
        "  exteriorColor { name } "
        "  transmission { label driveTrain { label } } "
        "  engine { fuel { label } } "
        "  body { frameStyle { label } } "
        "} } } }"
    )

    try:
        headers = {
            **REQUEST_HEADERS,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": dealer_config["base_url"],
            "Referer": dealer_config["inventory_url"],
        }

        resp = requests.post(
            graphql_url,
            headers=headers,
            json={"query": query},
            timeout=REQUEST_TIMEOUT,
        )

        if resp.status_code != 200:
            logger.warning(f"  SM360 GraphQL returned status {resp.status_code}")
            return []

        data = resp.json()
        if data.get("errors"):
            logger.warning(f"  SM360 GraphQL errors: {data['errors']}")
            return []

        result = data.get("data", {}).get("searchVehicles", {})
        vehicle_list = result.get("nodes", [])
        total = result.get("totalCount", 0)

        if not vehicle_list:
            logger.warning(f"  SM360 GraphQL returned 0/{total} vehicles")
            return []

        base_url = dealer_config["base_url"]
        vehicles = []
        for item in vehicle_list:
            if item.get("sold"):
                continue

            v = Vehicle(dealer=dealer_name)
            v.vin = item.get("vin", "")
            v.stock_number = item.get("stockNo", "")
            v.year = str(item.get("year", ""))
            v.odometer = str(item.get("odometer", ""))

            # Nested name fields
            v.make = (item.get("make") or {}).get("name", "")
            v.model = (item.get("model") or {}).get("name", "")
            v.trim = (item.get("trim") or {}).get("name", "")

            # Prices — stored as floats like 75900.0
            prices = item.get("prices") or {}
            sale_price = prices.get("sale")
            if sale_price:
                v.price = f"${int(sale_price)}"

            # Mileage from odometer (already in km)
            v.mileage = str(item.get("odometer", ""))

            # Characteristics
            chars = item.get("characteristics") or {}
            v.colour = (chars.get("exteriorColor") or {}).get("name", "")

            trans = chars.get("transmission") or {}
            v.transmission = trans.get("label") or ""
            v.drivetrain = (trans.get("driveTrain") or {}).get("label", "")

            engine = chars.get("engine") or {}
            v.fuel_type = (engine.get("fuel") or {}).get("label", "")

            body = chars.get("body") or {}
            v.body_type = (body.get("frameStyle") or {}).get("label", "")

            # Thumbnail image from SM360 CDN (resized via /ir/ endpoint)
            mm = item.get("multimedia") or {}
            main_pic = mm.get("mainPicture") or {}
            pic_path = main_pic.get("url", "")
            if pic_path:
                v.image_url = f"https://img.sm360.ca/ir/w400h300c/images/inventory{pic_path}"

            # Build detail URL from template
            vehicle_id = item.get("id", "")
            make_slug = v.make.lower().replace(" ", "-") if v.make else ""
            model_slug = v.model.lower().replace(" ", "-") if v.model else ""
            v.url = base_url + vdp_template.format(
                make=make_slug, model=model_slug,
                year=v.year, vehicleId=vehicle_id,
            )

            if v.vin:
                vehicles.append(v)

        logger.info(f"  SM360 GraphQL returned {len(vehicles)}/{total} vehicles")
        return vehicles

    except Exception as e:
        logger.warning(f"  SM360 GraphQL failed: {e}")
        return []


def _scrape_sm360_api(dealer_config: dict) -> list[Vehicle]:
    """Try to scrape SM360 via the REST vehicles API."""
    dealer_name = dealer_config["name"]
    api_url = dealer_config.get("api_url")
    api_params = dealer_config.get("api_params", {})

    if not api_url:
        return []

    try:
        # The SM360 API expects specific headers and a POST body
        headers = {
            **REQUEST_HEADERS,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": dealer_config["base_url"],
            "Referer": dealer_config["inventory_url"],
        }

        body = {
            "condition": "used",
            "bodyType": [],
            "make": [],
            "model": [],
            "year": {},
            "price": {},
            "mileage": {},
            "sortBy": "SALE_PRICE_ASC",
        }

        resp = requests.post(
            api_url,
            params=api_params,
            headers=headers,
            json=body,
            timeout=REQUEST_TIMEOUT,
        )

        if resp.status_code != 200:
            logger.warning(f"  SM360 REST API returned status {resp.status_code}")
            return []

        if not resp.text.strip():
            logger.warning(f"  SM360 REST API returned empty response")
            return []

        data = resp.json()

        # Try different response structures
        vehicle_list = data if isinstance(data, list) else data.get("vehicles", data.get("results", []))

        if not vehicle_list:
            logger.warning(f"  SM360 API returned no vehicles")
            return []

        vehicles = []
        for item in vehicle_list:
            v = Vehicle(dealer=dealer_name)
            v.year = str(item.get("year", ""))
            v.make = item.get("make", {}).get("name", "") if isinstance(item.get("make"), dict) else str(item.get("make", ""))
            v.model = item.get("model", {}).get("name", "") if isinstance(item.get("model"), dict) else str(item.get("model", ""))
            v.trim = item.get("trim", {}).get("name", "") if isinstance(item.get("trim"), dict) else str(item.get("trim", ""))
            v.price = _clean_price(str(item.get("salePrice", item.get("price", ""))))
            v.mileage = str(item.get("mileage", item.get("odometer", "")))
            v.vin = item.get("vin", "")
            v.stock_number = item.get("stockNumber", "")
            v.body_type = item.get("bodyType", {}).get("name", "") if isinstance(item.get("bodyType"), dict) else str(item.get("bodyType", ""))
            v.drivetrain = item.get("drivetrain", "")
            v.transmission = item.get("transmission", "")
            v.fuel_type = item.get("fuelType", "")
            v.colour = item.get("exteriorColor", "")
            v.url = item.get("url", f"{dealer_config['base_url']}/en/used-inventory")
            if v.vin:
                vehicles.append(v)

        logger.info(f"  SM360 API returned {len(vehicles)} vehicles")
        return vehicles

    except Exception as e:
        logger.warning(f"  SM360 API failed: {e}")
        return []


def _scrape_sm360_html(dealer_config: dict) -> list[Vehicle]:
    """Fallback: scrape SM360 by parsing the HTML page."""
    dealer_name = dealer_config["name"]
    base_url = dealer_config["base_url"]
    inventory_url = dealer_config["inventory_url"]

    soup = _get_page(inventory_url)
    if not soup:
        return []

    # SM360 renders tiles with class listing-tile-link
    tiles = soup.select(".listing-tile-link")

    # If no tiles found, the content is JS-rendered. Try alternative selectors.
    if not tiles:
        tiles = soup.select(".ThemedTile")
    if not tiles:
        tiles = soup.select("[class*='tile']")
    if not tiles:
        logger.warning(f"  No vehicle tiles found in HTML for {dealer_name}. "
                       f"This site likely requires JavaScript rendering.")
        # Fallback: parse whatever structured data we can find in the raw HTML
        return _scrape_sm360_from_raw_html(soup, dealer_config)

    logger.info(f"  Found {len(tiles)} vehicle tiles in HTML")

    vehicles = []
    for tile in tiles:
        v = _parse_sm360_tile(tile, dealer_name, base_url)
        if v and v.vin:
            vehicles.append(v)

    logger.info(f"  Parsed {len(vehicles)} vehicles with VINs")
    return vehicles


def _scrape_sm360_from_raw_html(soup: BeautifulSoup, dealer_config: dict) -> list[Vehicle]:
    """Last resort: extract VINs and basic info from raw page HTML/text."""
    dealer_name = dealer_config["name"]
    base_url = dealer_config["base_url"]
    text = soup.get_text()

    # Find all VINs
    vins = re.findall(r"VIN\s+(\w{17})", text)
    if not vins:
        vins = re.findall(r"\b([A-HJ-NPR-Z0-9]{17})\b", text)

    # Find all year/make/model patterns
    entries = re.findall(r"(\d{4})\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+([A-Za-z][\w\s-]+?)(?:\n|VIN|#)", text)

    vehicles = []
    for i, vin in enumerate(vins):
        v = Vehicle(dealer=dealer_name, vin=vin, url=f"{base_url}/en/used-inventory")
        if i < len(entries):
            v.year, v.make, v.model = entries[i]
            v.model = v.model.strip()
        vehicles.append(v)

    # Find prices and mileages
    prices = re.findall(r"\*?\$[\d,]+", text)
    mileages = re.findall(r"([\d,]+)\s*km", text, re.IGNORECASE)

    for i, v in enumerate(vehicles):
        if i < len(prices):
            v.price = _clean_price(prices[i])
        if i < len(mileages):
            v.mileage = mileages[i].replace(",", "")

    logger.info(f"  Raw HTML parse found {len(vehicles)} vehicles")
    return vehicles
