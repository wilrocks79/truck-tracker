"""
Configuration for Squamish truck inventory tracker.
"""

import os

# Optional HTTP proxy for environments where direct requests get blocked (e.g.
# GitHub Actions datacenter IPs).  Set the SCRAPER_PROXY env var to a proxy URL
# like "http://user:pass@proxy-host:port" and all outbound requests will be
# routed through it.
SCRAPER_PROXY = os.environ.get("SCRAPER_PROXY", "")

DEALERS = {
    "squamish_toyota": {
        "name": "Squamish Toyota",
        "platform": "edealer",
        "base_url": "https://www.squamishtoyota.com",
        "inventory_url": "https://www.squamishtoyota.com/inventory/used/",
    },
    "greg_gardner_gm": {
        "name": "Greg Gardner Motors",
        "platform": "edealer",
        "base_url": "https://www.greggardnergm.com",
        "inventory_url": "https://www.greggardnergm.com/inventory/used/",
    },
    "coastal_ford": {
        "name": "Coastal Ford Squamish",
        "platform": "sm360",
        "base_url": "https://www.coastalfordsquamish.com",
        "inventory_url": "https://www.coastalfordsquamish.com/en/used-inventory",
        "graphql_url": "https://webauto-supplier-api.sm360.ca/webauto/graphql",
        "vdp_url": "/en/used-inventory/{make}/{model}/{year}-{make}-{model}-id{vehicleId}",
        "api_params": {
            "organizationId": "7451",
            "organizationUnitId": "10278",
        },
    },
}

# Body types considered "trucks"
TRUCK_BODY_TYPES = [
    "truck", "pickup", "crew cab", "double cab", "regular cab",
    "extended cab", "supercrew", "supercab", "quad cab", "king cab",
    "access cab", "pickup - crew cab", "pickup - regular cab",
    "pickup - extended cab",
]

# Common truck model names to match broadly
TRUCK_MODELS = [
    "f-150", "f150", "f-250", "f250", "f-350", "f350", "f-450", "f450",
    "ranger", "maverick",
    "silverado", "colorado", "sierra",
    "ram", "ram 1500", "ram 2500", "ram 3500",
    "tacoma", "tundra",
    "frontier", "titan",
    "ridgeline",
    "canyon",
    "gladiator",
    "santa cruz",
    "cybertruck",
    "lightning",
    "rivian",
]

# Request settings
REQUEST_TIMEOUT = 30
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
REQUEST_PROXIES = (
    {"http": SCRAPER_PROXY, "https": SCRAPER_PROXY} if SCRAPER_PROXY else None
)

# Data files
DATA_DIR = "data"
INVENTORY_CSV = f"{DATA_DIR}/inventory.csv"
HISTORY_CSV = f"{DATA_DIR}/price_history.csv"
LOG_FILE = f"{DATA_DIR}/scraper.log"
