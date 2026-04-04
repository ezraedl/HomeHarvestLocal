"""
Scrape a single-family property by address and save as JSON.

Edit `ADDRESS` below, then run from the `HomeHarvestLocal/` directory:
  python examples/single_family_address_to_json.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure we use the local `HomeHarvestLocal/homeharvest` package (not a pip install).
HOMEHARVEST_LOCAL_ROOT = Path(__file__).resolve().parents[1]
if str(HOMEHARVEST_LOCAL_ROOT) not in sys.path:
    sys.path.insert(0, str(HOMEHARVEST_LOCAL_ROOT))

from homeharvest import scrape_property


# Example address (replace with the one you want).
# You can use formats like:
# - "1234 Main St, San Diego, CA 92104"
# - "San Diego, CA 92104" (if the API resolves it to an address-like geo result)
#ADDRESS = "2051 W 18th St, Cleveland, OH 44113"

ADDRESS = "1059 E 76th St, Cleveland, OH 44103"

def _safe_filename(s: str, max_len: int = 90) -> str:
    # Keep filenames readable while stripping characters that often break paths.
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ")
    cleaned = "".join(ch if ch in allowed else "_" for ch in s).strip()
    cleaned = cleaned.replace(" ", "_")
    return cleaned[:max_len] if len(cleaned) > max_len else cleaned


def main() -> None:
    listing_type = "for_sale"

    # For a single address (no radius), RealtorScraper typically returns 0 or 1 home
    # when `return_type="raw"` (we get a list of dicts ready for JSON).
    results = scrape_property(
        location=ADDRESS,
        listing_type=listing_type,
        property_type=["single_family"],
        return_type="raw",
        # Limit applies to pagination in general searches; it should not matter for
        # single-address non-comps lookups, but it keeps behavior consistent.
        limit=10,
    )

    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_path = os.path.join(output_dir, f"{_safe_filename(ADDRESS)}_{listing_type}_{ts}.json")

    payload = {
        "query": {
            "address": ADDRESS,
            "listing_type": listing_type,
            "property_type": ["single_family"],
            "return_type": "raw",
        },
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    # `default=str` is a safety net in case any nested values aren't JSON-serializable.
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    print(f"Saved {len(results)} result(s) to: {out_path}")


if __name__ == "__main__":
    main()

