#!/usr/bin/env python3
"""Export enriched subreddits from communities.json to a browsable directory JSON.

Filters to: subscribers >= 100K, no enrich_error, not over18, valid name/description.
Output: backend/app/data/subreddits_directory.json (~6K entries, ~2-3 MB)
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
INPUT_PATH = SCRIPT_DIR / "communities.json"
OUTPUT_PATH = SCRIPT_DIR.parent.parent / "backend" / "app" / "data" / "subreddits_directory.json"

MIN_SUBSCRIBERS = 100_000


def main():
    with open(INPUT_PATH) as f:
        data = json.load(f)

    entries = []
    for entry in data:
        subs = entry.get("subscribers")
        if not subs or subs < MIN_SUBSCRIBERS:
            continue
        if entry.get("enrich_error"):
            continue
        if entry.get("over18"):
            continue
        name = entry.get("name", "").strip()
        if not name:
            continue

        entries.append({
            "name": name,
            "description": (entry.get("description") or "")[:200],
            "subscribers": subs,
            "icon_url": entry.get("icon_url") or None,
        })

    # Sort by subscriber count descending
    entries.sort(key=lambda e: e["subscribers"], reverse=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(entries, f, separators=(",", ":"))

    print(f"Exported {len(entries)} subreddits to {OUTPUT_PATH}")
    print(f"File size: {OUTPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
