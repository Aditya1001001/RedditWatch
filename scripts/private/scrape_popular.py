#!/usr/bin/env python3
"""Scrape Reddit's community directory with activity checking.

Three phases:
  Phase 1: Scrape /best/communities/{page} HTML pages for subreddit names
           (~250 subs/page, ~1451 pages, ~362K total subreddits)
  Phase 2: Enrich each sub with details from /r/{name}/about.json
           (description, subscribers, icon, etc.)
  Phase 3: Check each subreddit's latest post for activity flags
           (post_in_last_week, post_in_last_month)

Progress is saved incrementally — safe to Ctrl+C and resume.

Usage:
    # Full run (all 3 phases)
    python scripts/private/scrape_popular.py

    # Just scrape names (fast, HTML only)
    python scripts/private/scrape_popular.py --names-only

    # Enrich existing names with details
    python scripts/private/scrape_popular.py --enrich-only

    # Only check activity on existing data
    python scripts/private/scrape_popular.py --activity-only
"""

import argparse
import asyncio
import json
import random
import re
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from app.collectors.reddit import RedditCollector  # noqa: E402
from app.services.collector import CollectorService  # noqa: E402

# Graceful shutdown on Ctrl+C
_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n[!] Shutdown requested — saving progress and exiting...")


signal.signal(signal.SIGINT, _handle_signal)


def save_json(path: Path, data: list) -> None:
    """Atomic write via tmp file rename."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


def load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


# ---------------------------------------------------------------------------
# Phase 1: Scrape subreddit names from /best/communities/ HTML
# ---------------------------------------------------------------------------

async def phase1_scrape_names(
    collector: RedditCollector,
    max_page: int,
    output: Path,
    start_page: int = 1,
) -> list[dict]:
    """Scrape subreddit names from Reddit's community directory HTML pages."""
    global _shutdown

    existing = load_json(output)
    seen_names = {s["name"].lower() for s in existing}
    all_subs = list(existing)
    new_this_run = 0

    if existing:
        print(f"  Found {len(existing)} subs on disk (deduplicating)")

    # Pages are numbered 1, 2, 3, ... with 250 subs per page
    page = start_page
    while page <= max_page:
        if _shutdown:
            break

        url = f"https://www.reddit.com/best/communities/{page}/"

        try:
            response = await collector._request(url)

            if response.status_code == 429:
                print(f"  Rate limited on page {page} — pausing 120s...")
                await asyncio.sleep(120)
                continue  # retry same page

            if response.status_code != 200:
                print(f"  Page {page} failed: HTTP {response.status_code}")
                break

            html = response.text

            # Extract subreddit names from href="/r/{name}/" links
            names = re.findall(r'href="/r/([A-Za-z0-9_]+)/"', html)
            unique_page = list(dict.fromkeys(names))  # dedupe preserving order

            # Extract community IDs for reference
            ids = re.findall(r'community-id="(t5_[^"]+)"', html)

            page_new = 0
            for idx, name in enumerate(unique_page):
                if name.lower() in seen_names:
                    continue
                entry = {
                    "name": name,
                    "community_id": ids[idx] if idx < len(ids) else None,
                }
                all_subs.append(entry)
                seen_names.add(name.lower())
                page_new += 1
                new_this_run += 1

            print(
                f"  Page {page}/{max_page}: "
                f"+{page_new} new, {len(unique_page)} on page "
                f"(total: {len(all_subs)})"
            )

            # Stop if page had no subs (end of directory)
            if len(unique_page) == 0:
                print("  Empty page — reached end of directory")
                break

            # Save progress every 10 pages
            if page % 10 == 0:
                save_json(output, all_subs)

            # Pauses between pages (HTML scraping is lightweight)
            if page % 200 == 0:
                pause = random.uniform(30, 60)
                print(f"  Long pause: {pause:.0f}s (every 200 pages)")
                await asyncio.sleep(pause)
            else:
                await asyncio.sleep(random.uniform(1, 2.5))

        except Exception as e:
            import traceback
            print(f"  Error on page {page}: {e}")
            traceback.print_exc()
            save_json(output, all_subs)
            # Pause and retry once before giving up
            print(f"  Retrying page {page} after 30s...")
            await asyncio.sleep(30)
            try:
                response = await collector._request(url)
                if response.status_code == 200:
                    print(f"  Retry succeeded, continuing...")
                    page += 1
                    continue
            except Exception:
                pass
            print(f"  Retry failed, stopping.")
            break

        page += 1

    save_json(output, all_subs)
    print(f"Phase 1 done: {len(all_subs)} total ({new_this_run} new this run)")
    return all_subs


# ---------------------------------------------------------------------------
# Phase 2: Enrich with /about.json (description, subscribers, icon)
# ---------------------------------------------------------------------------

async def phase2_enrich(
    collector: RedditCollector,
    subs: list[dict],
    output: Path,
) -> None:
    """Fetch details for each subreddit via /about.json."""
    global _shutdown

    # Only enrich subs that don't have subscribers yet
    remaining = [s for s in subs if "subscribers" not in s]
    done_count = len(subs) - len(remaining)

    print(
        f"\nPhase 2: enriching {len(remaining)} subs "
        f"({done_count} already enriched)",
        flush=True,
    )

    for i, sub in enumerate(remaining):
        if _shutdown:
            break

        try:
            response = await collector._request(
                f"{collector.base_url}/r/{sub['name']}/about.json",
            )

            if response.status_code == 429:
                print(f"  Rate limited at r/{sub['name']} — pausing 120s...")
                save_json(output, subs)
                await asyncio.sleep(120)
                response = await collector._request(
                    f"{collector.base_url}/r/{sub['name']}/about.json",
                )

            if response.status_code == 200:
                sd = response.json().get("data", {})

                # Icon extraction
                icon_url = None
                ci = sd.get("community_icon") or ""
                if ci:
                    icon_url = ci.split("?")[0]
                if not icon_url:
                    icon_url = sd.get("icon_img") or None

                sub["description"] = (sd.get("public_description") or "")[:500]
                sub["description_full"] = sd.get("description") or ""
                sub["subscribers"] = sd.get("subscribers", 0)
                sub["icon_url"] = icon_url
                sub["active_users"] = (
                    sd.get("accounts_active")
                    or sd.get("active_user_count")
                    or 0
                )
                sub["over18"] = sd.get("over18", False)
                sub["created_utc"] = sd.get("created_utc")
            else:
                # Mark as enriched but with no data (private/banned/etc)
                sub["subscribers"] = 0
                sub["description"] = ""
                sub["enrich_error"] = response.status_code

        except Exception as e:
            print(f"  Error for r/{sub['name']}: {e}")
            sub["subscribers"] = 0
            sub["enrich_error"] = str(e)

        total_done = done_count + i + 1
        pct = total_done / len(subs) * 100
        subs_count = sub.get("subscribers", 0)
        print(
            f"  [{pct:5.1f}%] {total_done:,}/{len(subs):,} "
            f"r/{sub['name']} ({subs_count:,} subs)",
            flush=True,
        )

        # Save every 100
        if (i + 1) % 100 == 0:
            save_json(output, subs)
            print(f"  — saved", flush=True)

        # Rate limiter handles pacing — just add a long pause every 1000
        if (i + 1) % 1000 == 0:
            pause = random.uniform(30, 60)
            print(f"  Pause: {pause:.0f}s (every 1000 enrichments)", flush=True)
            await asyncio.sleep(pause)

    save_json(output, subs)

    enriched = sum(1 for s in subs if "subscribers" in s)
    with_icon = sum(1 for s in subs if s.get("icon_url"))
    print(f"Phase 2 done: {enriched}/{len(subs)} enriched, {with_icon} with icons")


# ---------------------------------------------------------------------------
# Phase 3: Check latest post for activity flags
# ---------------------------------------------------------------------------

async def phase3_check_activity(
    collector: RedditCollector,
    subs: list[dict],
    output: Path,
) -> None:
    """Check latest post date for each subreddit."""
    global _shutdown

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    remaining = [s for s in subs if "post_in_last_week" not in s]
    done_count = len(subs) - len(remaining)

    print(
        f"\nPhase 3: checking activity for {len(remaining)} subs "
        f"({done_count} already done)"
    )

    for i, sub in enumerate(remaining):
        if _shutdown:
            break

        try:
            response = await collector._request(
                f"{collector.base_url}/r/{sub['name']}/new.json",
                params={"limit": 1},
            )

            if response.status_code == 429:
                print(f"  Rate limited at r/{sub['name']} — pausing 120s...")
                save_json(output, subs)
                await asyncio.sleep(120)
                response = await collector._request(
                    f"{collector.base_url}/r/{sub['name']}/new.json",
                    params={"limit": 1},
                )

            newest_dt = None
            if response.status_code == 200:
                children = response.json().get("data", {}).get("children", [])
                if children and children[0].get("kind") == "t3":
                    ts = children[0].get("data", {}).get("created_utc")
                    if ts:
                        newest_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            sub["newest_post_utc"] = newest_dt.isoformat() if newest_dt else None
            sub["post_in_last_week"] = bool(newest_dt and newest_dt >= week_ago)
            sub["post_in_last_month"] = bool(newest_dt and newest_dt >= month_ago)

        except Exception as e:
            print(f"  Error for r/{sub['name']}: {e}")
            sub["newest_post_utc"] = None
            sub["post_in_last_week"] = None
            sub["post_in_last_month"] = None

        total_done = done_count + i + 1
        if (i + 1) % 50 == 0:
            pct = total_done / len(subs) * 100
            active = sum(1 for s in subs if s.get("post_in_last_week") is True)
            print(
                f"  [{pct:5.1f}%] {total_done}/{len(subs)} checked "
                f"— {active} active this week"
            )

        # Save every 100
        if (i + 1) % 100 == 0:
            save_json(output, subs)

        # Pauses (conservative)
        if (i + 1) % 500 == 0:
            pause = random.uniform(60, 120)
            print(f"  Long pause: {pause:.0f}s (every 500 checks)")
            await asyncio.sleep(pause)
        elif (i + 1) % 100 == 0:
            await asyncio.sleep(random.uniform(15, 30))
        else:
            await asyncio.sleep(random.uniform(3, 8))

    save_json(output, subs)

    active_week = sum(1 for s in subs if s.get("post_in_last_week") is True)
    active_month = sum(1 for s in subs if s.get("post_in_last_month") is True)
    checked = sum(1 for s in subs if "post_in_last_week" in s)
    print(f"Phase 3 done: {checked}/{len(subs)} checked")
    print(f"  Active in last week:  {active_week}")
    print(f"  Active in last month: {active_month}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    # Phase 1 is HTML scraping (light), phases 2/3 are JSON API (heavier)
    if args.names_only or not (args.enrich_only or args.activity_only):
        rpm = 15.0
    else:
        rpm = args.rpm
    collector = RedditCollector(rate_limit_rpm=rpm)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Determine what to run
        if args.enrich_only:
            subs = load_json(output_path)
            if not subs:
                print("No existing data — run without --enrich-only first")
                return
            print(f"Loaded {len(subs)} subs from {output_path}")
            await phase2_enrich(collector, subs, output_path)
        elif args.activity_only:
            subs = load_json(output_path)
            if not subs:
                print("No existing data — run without --activity-only first")
                return
            print(f"Loaded {len(subs)} subs from {output_path}")
            await phase3_check_activity(collector, subs, output_path)
        else:
            # Phase 1: scrape names
            print(f"Phase 1: scraping community directory (pages {args.start_page}–{args.max_page})...")
            subs = await phase1_scrape_names(
                collector, args.max_page, output_path, start_page=args.start_page
            )

            # Catalog overlap summary
            svc = CollectorService()
            catalog_names = {e["name"].lower() for e in svc.get_catalog_flat()}
            fetched_names = {s["name"].lower() for s in subs}
            print(f"  In catalog: {len(fetched_names & catalog_names)}")
            print(f"  New:        {len(fetched_names - catalog_names)}")

            # Phase 2: enrich (unless --names-only)
            if not args.names_only and not _shutdown:
                await phase2_enrich(collector, subs, output_path)

            # Phase 3: activity (unless --names-only or --skip-activity)
            if not args.names_only and not args.skip_activity and not _shutdown:
                await phase3_check_activity(collector, subs, output_path)

        print(f"\nOutput: {output_path}")
    finally:
        await collector.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Reddit community directory with enrichment + activity checking"
    )
    parser.add_argument(
        "--max-page",
        type=int,
        default=1500,
        help="Max page number for /best/communities/ (250 subs/page, default 1500)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Page to start from (for resuming, default 1)",
    )
    parser.add_argument(
        "--rpm",
        type=float,
        default=2.0,
        help="Requests per minute for API phases (default 2.0)",
    )
    parser.add_argument(
        "--output",
        default="scripts/private/popular_subreddits.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="Only run phase 1 (scrape names, skip enrichment + activity)",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only run phase 2 (enrich existing names with details)",
    )
    parser.add_argument(
        "--skip-activity",
        action="store_true",
        help="Skip phase 3 (activity checking)",
    )
    parser.add_argument(
        "--activity-only",
        action="store_true",
        help="Only run phase 3 on existing data",
    )
    args = parser.parse_args()
    asyncio.run(main(args))
