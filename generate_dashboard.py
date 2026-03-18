#!/usr/bin/env python3
"""
Generate the truck tracker dashboard HTML with live data injected.

Reads inventory.csv and price_history.csv, converts to JSON,
and injects into dashboard.html → outputs data/dashboard.html.

Usage:
    python generate_dashboard.py          # Generate dashboard
    python generate_dashboard.py --open   # Generate and open in browser
"""

import csv
import json
import os
import sys
import webbrowser
from datetime import datetime

# Ensure we run from the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import INVENTORY_CSV, HISTORY_CSV, DATA_DIR


def load_csv(path: str) -> list[dict]:
    """Load a CSV file into a list of dicts."""
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def generate():
    """Read template, inject data, write output."""
    inventory = load_csv(INVENTORY_CSV)
    history = load_csv(HISTORY_CSV)

    # Read the template
    template_path = "dashboard.html"
    if not os.path.exists(template_path):
        print(f"ERROR: {template_path} not found", file=sys.stderr)
        return None

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Build the data injection script
    data_script = f"""
const INVENTORY = {json.dumps(inventory, indent=2)};
const PRICE_HISTORY = {json.dumps(history, indent=2)};
const LAST_UPDATED = "{datetime.now().strftime('%Y-%m-%d %H:%M')}";
"""

    # Replace the placeholder block
    html = html.replace(
        """// __TRUCK_DATA_INJECT__
const INVENTORY = [];
const PRICE_HISTORY = [];
const LAST_UPDATED = "";""",
        data_script.strip(),
    )

    # Write output
    output_path = os.path.join(DATA_DIR, "dashboard.html")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    print(f"  {len(inventory)} inventory records")
    print(f"  {len(history)} history events")
    return os.path.abspath(output_path)


if __name__ == "__main__":
    path = generate()
    if path and "--open" in sys.argv:
        webbrowser.open(f"file://{path}")
