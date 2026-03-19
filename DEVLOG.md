# RedditWatch Development Log

## Project Overview

**Goal**: Build a self-hosted alternative to GummySearch/PainOnSocial for Reddit market research.

**Why**: GummySearch shut down (Nov 2025), paid alternatives cost $20-200/month, and we want to own our data and run offline with local LLMs.

**Status**: Phase 12 complete (Smart Startup Collection) | Mac app planned (Phase 13)

---

## Pending Work

### Phase 11: Reddit OAuth + Rate Limit Hardening

**Problem**: Currently scraping `old.reddit.com` JSON with no authentication. Unauthenticated rate limit is ~10 req/min per IP. Authenticated OAuth API allows 100 req/min — 10x improvement. This is the root cause of the rate limit failures during data collection (only r/indiehackers got deep collection, others got ~23 posts each).

**Current vulnerabilities:**
- No OAuth — operating at 1/10th allowed throughput
- Comment fetching silently fails on 429 (no retry, no backoff)
- No global rate limiter — concurrent tasks can spike requests
- No parsing of `X-RateLimit-Remaining`/`X-RateLimit-Reset` headers
- No retry queue — failed requests are permanently lost
- `client_id`/`client_secret` exist in config but are never used

**Plan:**
- [ ] Register Reddit "script" app at reddit.com/prefs/apps
- [ ] Implement OAuth client credentials flow (bearer token with auto-refresh)
- [ ] Switch endpoints from `old.reddit.com/*.json` to `oauth.reddit.com/r/*`
- [ ] Add global token-bucket rate limiter (shared across all concurrent tasks)
- [ ] Parse `X-RateLimit-*` response headers for precise throttling
- [ ] Add consistent exponential backoff for comments (match posts behavior)
- [ ] Add retry queue for failed fetches (persist to DB, retry on next run)
- [ ] Validate config limits (cap `concurrent_subreddits`, `max_pages_per_sort`)
- [ ] Re-collect data for 8 subreddits that only got ~23 posts
- [ ] Retry r/smallbusiness (was fully blocked)

### Phase 12: UI/UX Audit Fixes (Insights + Analytics Tabs)

**Problem**: Insights and Analytics tabs have unclear boundaries, redundant elements, and several items that are developer-facing rather than user-facing.

**Insights tab fixes:**
- [ ] Replace "Avg Time" stat with actionable metric (e.g. "Products Mentioned")
- [ ] Replace "Total Posts" + "Analyzed" with insight-oriented metrics (Pain Points, Opportunities, etc.)
- [ ] Reduce prominence of Analyze bar — show only when unanalyzed posts exist
- [ ] Drop Insight Types horizontal bar chart (redundant with Analytics doughnut + filter buttons)
- [ ] Replace opaque theme "combined_score" with plain-language labels
- [ ] Add pagination to insights list (currently hard-capped at 50)
- [ ] Replace search similarity % with human-readable relevance indicator

**Analytics tab — remove (redundant or not useful):**
- [ ] Insight Distribution doughnut (same data as Insights tab filter buttons)
- [ ] Top Themes bar chart (same data as Insights tab themes list)
- [ ] Posts by Subreddit bar (already on Dashboard)
- [ ] Theme Intensity scatter (confusing, redundant encoding)
- [ ] Collection Timeline (operational, not analytical)
- [ ] Subscriber Growth (already on Subreddits tab)
- [ ] Theme Co-occurrence network (rarely actionable, adds D3.js 250KB dependency)

**Analytics tab — keep and improve:**
- [ ] Theme Trends line chart (most valuable — make more prominent)
- [ ] Activity Heatmap (useful for posting strategy — add timezone note)
- [ ] Subreddit × Theme Matrix (simplify to top 5×5, clearer color scale)
- [ ] Highest Intensity Insights table (good "highlights reel")

**General:**
- [ ] Wire audience filter to all analytics API calls (currently missing)
- [ ] Deduplicate summary metrics between tabs

### Phase 13: Native Mac App

**Goal**: Package RedditWatch as a native macOS app so it can run persistently in the background — collecting data, running analysis — without the user needing a terminal or browser tab open.

**Why**:
- Desktop app can run collection on a schedule in the background (menu bar agent)
- No need for `python -m uvicorn` — double-click to launch
- Startup catch-up collection (Phase 12) becomes even better: the app is always warm
- Natural distribution path: `.dmg` download, drag to Applications

**Options to evaluate**:
- **Tauri** — native macOS window (WebKit), Python backend as sidecar. Tiny binary, best UX.
- **PyWebView** — pure Python, wraps native WebKit. Simplest to ship, no JS toolchain.
- **Swift + WKWebView** — fully native wrapper, best macOS integration (menu bar, notifications)

**Key features for Mac app**:
- [ ] Menu bar icon with status (idle / collecting / analyzing)
- [ ] Background collection on configurable schedule
- [ ] Native notifications on collection/analysis completion
- [ ] Launch at login option
- [ ] Bundled Python runtime (no system Python dependency)

### Other Pending Items

- [ ] Set up Claude API for faster analysis (~1,400 unanalyzed posts)
- [ ] Take fresh screenshots after analysis + UI fixes
- [x] Review subreddit catalog category groupings (287 → 46 categories, 1,859 → 263 curated subs)
- [ ] Address remaining codebase audit items (see audit section below)

---

## Changelog

### 2026-03-19: Smart Startup Collection for Intermittent Users

**Problem**: Most self-hosted users run RedditWatch intermittently — open it, check insights, close it. Data goes stale between sessions, and setting up cron jobs or external schedulers is friction nobody wants.

**Solution**: On app startup, automatically check how stale the data is. If any monitored subreddit hasn't been collected in >12 hours (configurable), trigger a background collection. Non-blocking — the app is immediately usable with existing data while fresh data streams in.

**Changes**:
- Added `collect_on_startup` (default: true) and `stale_threshold_hours` (default: 12) config options
- Added `CollectorService.get_staleness()` — checks oldest `last_collected` timestamp and never-collected count
- Added `_startup_collect_if_stale()` in lifespan — runs as background task via `TaskTracker` so frontend can track it
- Added collection-in-progress banner on Subreddits tab: "Collecting fresh data... X new posts so far"
- Banner auto-dismisses on completion and reloads data
- Coexists with existing `auto_schedule` — both can be active independently

### 2026-03-16: Rebuild Subreddit Catalog — Categories & Display

The bulk-imported catalog (1,859 subs across 287 categories from r/ListOfSubreddits wiki) was unusable — categories like `weird_feelingscategorize_later`, `neckbeard`, `sfwporn_network` cluttered the UI, and 287 pill buttons overflowed the screen.

**Catalog rebuild**
- Consolidated 287 categories → 46 clean categories covering business, tech, and lifestyle verticals
- Curated 1,859 subs → 263 market-research-relevant subs
- New YAML structure: `_meta.display_name` per category + `subreddits` list
- Every sub has `name`, `display_name`, `description`, `subscribers`, `best_for`
- Dropped purely entertainment/meme subs with zero market research value

**Backend changes**
- `collector.py`: `get_catalog_flat()` parses new `_meta` + `subreddits` structure, includes `category_display_name`
- `collector.py`: Added `get_catalog_categories()` returning `{key, display_name, count}` per category
- `subreddits.py`: `/catalog/categories` endpoint returns category objects instead of string keys
- `subreddits.py`: `CatalogEntry` model includes `category_display_name` field

**Frontend changes**
- Category pills show clean display names with counts: "Startups & Founders (8)" instead of "startups_founders"
- "All" pill shows total sub count
- Catalog cards show category label when viewing "All" (e.g. "· Marketing & Growth")
- Cards fall back to `description` if `best_for` is empty

---

### 2026-03-16: Private Monorepo + Public OSS Mirror

Set up a private/public repo split so SaaS-only features can be developed without exposing them in the open-source version.

**Repo Architecture**

- Created private repo `Aditya1001001/redditwatch-pro` — all development happens here now
- Public repo `Aditya1001001/RedditWatch` is now an auto-synced OSS mirror
- Local `origin` remote points to `redditwatch-pro`

**OSS Sync Workflow**

- `.github/workflows/sync-oss.yml` triggers on push to `main` in private repo
- Strips paths listed in `.oss-ignore` (cloud/, .oss-ignore, the workflow itself)
- Force-pushes cleaned tree to public `RedditWatch` repo via classic PAT (`OSS_REPO_TOKEN` secret)
- Gotcha: had to unset `http.extraheader` set by `actions/checkout` to allow cross-repo push

**Edition Toggle**

- `EDITION` env var (`"oss"` default, `"cloud"` for SaaS) read in `backend/app/config.py`
- `Config.is_cloud` property for easy checks
- `main.py` conditionally loads cloud routes when `EDITION=cloud`, gracefully falls back if cloud package missing

**SaaS-Only Code (`backend/app/cloud/`)**

- `auth/` — JWT/session auth (placeholder)
- `tenancy/` — user-scoped DB queries (placeholder)
- `historical/` — Arctic Shift collector (placeholder)
- `billing/` — Stripe/quotas (placeholder)

---

### 2026-03-16: Catalog Expansion & Data Collection

**Subreddit Catalog**
- Expanded from 117 → 1,859 subreddits across 287 categories
- Full import from r/ListOfSubreddits wiki HTML — covers every niche (pets, fitness, cooking, gaming, etc.)
- Rebuilt: consolidated 287 wiki categories → 46 clean categories, 1,859 → 263 curated subs (see changelog below)
- TODO: Take fresh screenshots after analysis completes (analytics tab has 4 new Phase 9 visualizations)
- TODO: Set up Claude API for faster analysis of remaining ~1,400 posts

**Initial Data Collection**
- Collected posts from 9 subreddits (indiehackers, saas, sideproject, selfhosted, startups, entrepreneur, microsaas, buildinpublic, webdev)
- r/indiehackers: 1,383 posts (deep collect), others: ~23 each (single page due to rate limits)
- Total: 1,592 posts, 4,679 comments
- r/smallbusiness blocked by rate limits — retry needed
- Note: concurrent collection causes SQLite locks + burns Reddit rate limits fast; sequential + cooldown is more reliable

---

### 2026-03-16: Phase 9 — Advanced Visualizations

Added 4 new analytics visualizations with backend endpoints and frontend rendering.

**Theme Popularity Timeline**
- Line chart showing top 8 themes over time (daily insight counts)
- Backend: `GET /api/analyze/themes/timeline?days=30&top_n=8`
- Supports audience filtering

**Subreddit Activity Heatmap**
- Grid showing post counts by day-of-week × hour (UTC)
- Backend: `GET /api/posts/activity`
- GitHub-style green color scale

**Theme Co-occurrence Network**
- D3.js force-directed graph showing themes that appear together in the same post
- Backend: `GET /api/analyze/themes/co-occurrence?min_weight=1&top_n=15`
- Node size proportional to insight count, edge width proportional to co-occurrence weight

**Subreddit × Theme Matrix**
- Heatmap table showing insight counts per (subreddit, theme) pair
- Backend: `GET /api/analyze/themes/matrix?top_themes=10&top_subreddits=10`
- Color intensity scales with count

**Performance Fixes (from audit)**
- Fixed N+1 query in search API — batch SELECT instead of per-result session.get()
- Fixed N+1 in subreddit growth — single GROUP BY instead of per-subreddit loop
- Added composite indexes: (analyzed, created_utc), (subreddit, analyzed), comment_id, theme_id
- Narrowed exception handling in analyzer

---

### 2026-03-16: Codebase Audit

Full audit of backend and frontend before public launch. Prioritized findings below.

**Backend — High Priority**

- [ ] N+1 query in search API (`api/search.py:83-95`) — individual `session.get(Post, post_id)` per search result
- [ ] Missing composite indexes — `(analyzed, created_utc)`, `(subreddit, analyzed)`, `(post_id, created_utc)`
- [ ] N+1 in subreddit growth (`api/subreddits.py:145`) — individual query per subreddit for oldest snapshot
- [ ] Overly broad exception handling in analyzer — silently swallowing DB errors
- [ ] Inconsistent eager loading — mixing `selectinload()`/`joinedload()`

**Backend — Medium Priority**

- [ ] Missing composite index on `InsightTheme` for theme_id-only queries
- [ ] No partial index for `analyzed=False` post lookups
- [ ] Inconsistent pagination (page/page_size vs limit)
- [ ] Post body truncated to 500 chars in list response with no indicator
- [ ] Unvalidated subreddit names in growth endpoint (case sensitivity)
- [ ] No startup validation for LLM provider

**Frontend — High Priority**

- [ ] `getAudienceGrowth()` called 3x per render for same audience
- [ ] 20+ silent API failures — catch blocks set empty arrays, no user feedback
- [ ] No loading states on 6+ operations
- [ ] Task polling never times out — infinite retry if backend dies
- [ ] Race conditions — rapid audience switching can overwrite data with stale responses

**Frontend — Medium Priority**

- [ ] Monolithic 1,859-line HTML file — all JS inline
- [ ] 20+ duplicate error handling patterns
- [ ] No input validation on subreddit names, audience names, search queries
- [ ] Magic numbers / hardcoded limits throughout
- [ ] Dead code: `searchStats` loaded but never displayed
- [ ] Chart memory leaks on rapid tab switching
- [ ] Missing accessibility attributes (aria-label, alt, aria-live)

---

### 2026-03-16: Expanded Catalog & Audience Suggestions

Expanded the subreddit catalog from 53 to 117 subreddits across 20 categories, sourced from r/ListOfSubreddits wiki. Added audience-aware subreddit suggestions.

**Catalog Expansion**

- Added 11 new categories: cybersecurity, data analytics, gaming, health & fitness, education, creative media, careers & HR, crypto/web3, science & technology, personal finance & investing, lifestyle & hobbies
- Expanded industry verticals with Teachers, nursing, Truckers, RealEstate
- 117 total subreddits across 20 categories (was 53 across 9)
- Updated catalog subtitle from "startup research" to "market research"

**Audience Form Suggestions**

- When selecting subreddits for an audience, a "Suggested from catalog" section now appears with related subs from the same category
- Clicking a suggestion auto-adds it to monitored subreddits and selects it for the audience
- Shows up to 8 suggestions with hover tooltips showing each sub's `best_for` description

**Audience Card Growth Summary**

- Audience cards now show aggregate subscriber count and weighted-average growth % (e.g., "r/indiehackers, r/saas · 705K subscribers · ↑1.2%")
- Monitored subreddits header shows total subscriber count across all tracked subs
- New `getAudienceGrowth()` helper computes weighted stats from existing growth data

**Bug Fixes**

- Fixed `replace('_', ' ')` → `replaceAll('_', ' ')` so multi-underscore category names display correctly

---

### 2026-03-14: Phase 10 — Historical Data & UI Polish (Pre-Launch)

Two workstreams before public release:

**Track 3: Audience Groups (Multi-Subreddit Collections)**

- GummySearch's "Audience" feature was key — group multiple subreddits into a topic (e.g., "SaaS founders" = r/SaaS + r/startups + r/Entrepreneur)
- Current state: catalog has static `category` tags but no runtime grouping, insights API has no subreddit filter at all
- Need: `Audience` model, CRUD API, query posts/insights across groups, compare audiences
- Frontend: audience selector in dashboard, cross-audience analytics

**Track 4: Subreddit Growth Tracking**

- Current state: `subscribers` captured once at add time, never updated, no history
- Need: `SubscriberSnapshot` time-series model, scheduled refresh job, growth trend calculation
- Frontend: sparklines or growth indicators per subreddit

**Track 5: Hybrid Analysis (LLM + Rule-Based) — Deferred**

- Investigated what the LLM actually does in analysis (~60% requires LLM, ~40% could use simpler methods)
- Intensity scoring → keyword sentiment + engagement heuristics (score × comments)
- Sentiment → VADER/TextBlob library
- Product detection → known-product regex + spaCy NER
- Quote extraction → already fetching top comments by score, just pick the best
- Theme key generation → TF-IDF or keyword clustering (LLM gives cleaner labels though)
- Core LLM value: semantic classification (pain_point vs opportunity) and description generation
- **Plan**: Implement hybrid approach later — rule-based for intensity/sentiment/products/quotes, keep LLM for classification + description. Will cut LLM calls significantly.

**Track 1: Maximize Historical Data**

- Current Reddit collector limited to ~1,000 posts per sort/time combo via `old.reddit.com` JSON (max ~1 year via `top/year`)
- Researched **Arctic Shift** as primary source for deep historical data:
  - Free public API at `arctic-shift.photon-reddit.com` (successor to Pushshift)
  - Covers Reddit data from 2005–2025 via archived dumps
  - Endpoints: `/api/posts/search`, `/api/comments/search` with date-range cursors
  - Rate limit: ~2 req/sec, data lags ~36 hours behind live Reddit
  - Pagination via `created_utc` cursor for full subreddit history
- **PullPush** (`api.pullpush.io`) identified as fallback (Pushshift-compatible API, 15 req/min)
- Plan: Add Arctic Shift collector for one-time historical backfill, then continue using existing Reddit collector for incremental updates

**Track 2: UI Polish (Complete)**

- Installed **Impeccable** design skill (17 commands for AI-guided UI improvement)
- Captured "before" screenshots of all 6 tabs (`screenshots/before/`)
- **Complete visual overhaul** of `frontend/index.html`:
  - **Typography**: Plus Jakarta Sans + Newsreader (serif for quotes). Modular type scale, `tabular-nums` for data, uppercase tracking section labels
  - **Color**: Warm-tinted surfaces (not pure gray), amber/gold accent palette, tinted transparent insight badges instead of solid blocks
  - **Layout**: Border-based containers replacing card-everything pattern, `gap-px` grid for metrics, varied spatial rhythm
  - **Interactions**: Toast notification system replacing `alert()`, spinner SVGs on async buttons, 150-300ms transitions with exponential easing, entrance animations
  - **Accessibility**: `:focus-visible` rings, `role="tablist"` + `aria-selected`, `prefers-reduced-motion` support
  - **Details**: Custom scrollbar, connection status indicator, helpful empty states with dashed borders, version badge
- Captured "after" screenshots (`screenshots/after/`)
- Bumped to v0.2, Phase 10

---

### 2026-02-13: Large-Scale Collection (Paginated Multi-Sort + Scheduler)

Scaled collection from ~25 posts/subreddit to 1,000+ via paginated multi-sort scraping, concurrent collection, and scheduled jobs.

**Sprint 1: Paginated Multi-Sort Collection + Seed Mode**

- **Paginated collection** (`collectors/reddit.py`):
  - New `collect_posts_paginated()` follows Reddit's `after` cursor across multiple pages (default 10 pages, up to 1,000 posts per sort/time combo)
  - Adaptive rate limiting: 1s base delay with exponential backoff on 429 errors
  - Configurable `time_filter` parameter (was hardcoded to `"week"`)
- **Deep collection** (`collectors/reddit.py`):
  - New `collect_posts_deep()` runs multiple sort/time combos (`hot`, `new`, `top/week`, `top/month`, `top/year`) and deduplicates results by post ID
  - Expected yield: ~1,000-1,500 unique posts per subreddit
- **Concurrent collection** (`services/collector.py`):
  - Replaced sequential `for subreddit in subreddits` with `asyncio.Semaphore`-bounded concurrency (default 3 concurrent subreddits)
  - New `collect_subreddit_deep()` for multi-sort collection with deduplication
  - New `seed_collection()` for one-time deep scrape of all monitored subreddits
  - **Selective comment fetching**: Only fetches comments for posts above `comment_min_score` threshold (default 5), avoiding hours of low-value comment collection
- **Seed endpoint** (`api/collect.py`):
  - `POST /api/collect/seed` triggers deep scrape of all monitored subreddits, returns task_id
  - Added `mode` query param to `POST /api/collect` (`regular` vs `deep`)
- **Config** (`config.py`, `config.yaml`):
  - `sort_modes`: configurable list of sort/time combos for deep collection
  - `max_pages_per_sort`: max pagination depth (default 10)
  - `deep_collect_enabled`, `concurrent_subreddits`, `rate_limit_delay`, `comment_min_score`
  - `auto_schedule`: toggle for scheduler (Sprint 2)

**Sprint 2: Scheduled Collection**

- **Scheduler service** (`services/scheduler.py`):
  - APScheduler `AsyncIOScheduler` with three jobs:
    - Regular collection every 30 min (hot + new, single page)
    - Deep collection daily at 3 AM (all sort/time combos with pagination)
    - Comment refresh every 2 hours (re-fetch comments for high-engagement posts)
  - Config toggle: `collection.auto_schedule`
- **Scheduler API** (`api/scheduler.py`):
  - `GET /api/scheduler/status` — all jobs, next run times, last results
  - `POST /api/scheduler/start` / `POST /api/scheduler/stop`
  - `POST /api/scheduler/trigger/{job_id}` — manually trigger a specific job
- **Lifespan integration** (`main.py`): Scheduler starts/stops with the app when `auto_schedule` is enabled
- **Collection status** (`api/collect.py`): `GET /api/collect/status` now shows real scheduler state

**Expected data volume**:
| Timeframe | Posts | How |
|-----------|-------|-----|
| After seed (Day 1) | ~50,000 | 50 subs x ~1,000 unique posts from 5 sort combos |
| End of Week 1 | ~70,000 | Seed + incremental (48 runs x ~400 new/run) |
| End of Month 1 | ~150,000+ | Continuous accumulation, deduped by Reddit ID |

### 2026-02-13: Phases 0-4 Implementation Complete

Implemented the full roadmap from codebase review through open-source release:

**Phase 0: Git Hygiene**
- Added `key.txt`, `key.txt.pub`, `GIT_SETUP.md` to `.gitignore`
- Cleaned secrets from tracking

**Phase 1: Security & Critical Bugs**
- **CORS**: Made configurable via `config.yaml` (was hardcoded `allow_origins=["*"]`)
- **Background tasks**: Collection and analysis now run async with task polling (`services/tasks.py`)
- **LLM validation**: Pydantic models validate all LLM output (type, intensity 0-100, theme_key normalization)
- **Rate limits**: Don't update `last_collected` when Reddit returns 0 posts
- **O(N^2) fix**: Theme aggregation rewritten with SQL GROUP BY (was loading all insights into Python)
- **Session safety**: `session.begin_nested()` savepoints isolate per-post analysis failures
- **Error types**: Fixed endpoints returning dicts instead of proper HTTPException(404)

**Phase 2: Input Validation & Data Integrity**
- Subreddit name validation: regex `^[a-zA-Z0-9_]{2,21}$`, strips `r/` prefix
- ChromaDB sync on delete: removing a post also removes its insights from vector store
- Auto-index after analysis: new insights immediately searchable (was requiring manual reindex)

**Phase 3: Testing Foundation**
- 48 tests across 4 test files (test_analyzer, test_tasks, test_subreddits, test_endpoints)
- pytest + pytest-asyncio with in-memory SQLite fixtures
- GitHub Actions CI on push/PR (Python 3.9, 3.11, 3.12 matrix)
- Fixed Pydantic v2 deprecations (`class Config` → `model_config`, `regex` → `pattern`)

**Phase 4: Open-Source Release**
- MIT License, Dockerfile, docker-compose.yml (+ Ollama override)
- `scripts/setup.sh` and `scripts/run.sh` for local install
- Overhauled README with Docker quickstart, badges, full API table
- CONTRIBUTING.md with dev setup, coding standards, PR process
- Implemented insights.py and themes.py (were stubs)

### 2026-02-13: Codebase Review & Development Roadmap

Comprehensive codebase review completed. Key findings:

- **13 critical/high issues identified** across security, performance, and data integrity
- **Security**: Exposed secrets (key.txt tracked in git), `allow_origins=["*"]` with credentials
- **Performance**: Blocking endpoints (collection/analysis block event loop, O(N^2) theme aggregation)
- **Data integrity**: Silent rate limit failures update `last_collected`, no LLM output validation, ChromaDB not synced on delete
- **Missing infrastructure**: No tests, no Docker, no CI/CD, placeholder API endpoints still in router

**Decision**: Balanced roadmap prioritizing security fixes and open-source release, then SaaS foundation.

**Roadmap phases**:
- Phase 0: Git hygiene & secrets cleanup
- Phase 1: Security & critical bug fixes (CORS, background tasks, validation)
- Phase 2: Input validation & data integrity
- Phase 3: Testing foundation (pytest, CI)
- Phase 4: Open-source release (Docker, LICENSE, README)
- Phase 5-7: Scheduler, performance, deployment hardening
- Phase 8-9: SaaS foundation (auth, billing) - future

---

## 🚨 Critical Development: Reddit API Access (2026-01-30)

### The Problem

Reddit has effectively shut down API access for new applications:
- New API key applications are being rejected (even for academics)
- PRAW/asyncpraw requires OAuth credentials that are no longer obtainable
- This blocks our original collection strategy

### The Solution: API-Free Collection

After investigation, we found **three working alternatives** that don't require API keys:

#### 1. old.reddit.com JSON Endpoints (Primary Method)
```bash
# Works without authentication!
curl "https://old.reddit.com/r/SaaS.json?limit=25"
```
- Returns full JSON with post metadata, scores, comments
- Rate limited (~60-100 requests before 429 errors)
- Best for structured data extraction

#### 2. RSS Feeds (Backup Method)
```bash
curl "https://www.reddit.com/r/SaaS/.rss"
```
- Returns Atom XML with recent posts
- Limited data (no scores, no comments)
- Most reliable, unlikely to be blocked

#### 3. old.reddit.com HTML Scraping (Fallback)
```bash
curl "https://old.reddit.com/r/SaaS/"
```
- Minimal HTML, easy to parse
- Works when JSON endpoints are rate-limited
- Most resilient long-term option

### Implementation Changes

**Before (PRAW-based)**:
```python
reddit = asyncpraw.Reddit(client_id=..., client_secret=...)
subreddit = await reddit.subreddit("SaaS")
async for post in subreddit.hot(limit=25):
    # process post
```

**After (HTTP-based)**:
```python
async with httpx.AsyncClient() as client:
    response = await client.get(
        "https://old.reddit.com/r/SaaS.json",
        params={"limit": 25},
        headers={"User-Agent": "RedditWatch/1.0"}
    )
    data = response.json()
    for post in data["data"]["children"]:
        # process post["data"]
```

### Advantages of New Approach

| Aspect | PRAW (Old) | HTTP JSON (New) |
|--------|------------|-----------------|
| API Keys Required | Yes | No |
| Setup Complexity | High (OAuth) | Zero |
| Rate Limits | Strict (600/10min) | Moderate (~100/session) |
| Reliability | Depends on Reddit approval | Works now |
| Comment Fetching | Easy | Requires separate request |
| Future-Proof | No (API changes) | More resilient |

### Rate Limit Mitigation

To avoid 429 errors:
1. **Delays between requests**: 2-3 seconds between subreddit fetches
2. **Caching**: Don't re-fetch recently collected posts
3. **Batch collection**: Collect once per hour, not continuously
4. **Fallback chain**: JSON → RSS → HTML scraping
5. **User-Agent rotation**: Vary the user agent string

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Browser                               │
│                    (Alpine.js + Tailwind CSS + Chart.js)             │
│   Tabs: Dashboard | Subreddits | Posts | Insights | LLM | Analytics │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │Posts API │ │Subreddits│ │ Analyze  │ │ Search   │ │  LLM     │  │
│  │          │ │   API    │ │   API    │ │   API    │ │  API     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │              │            │            │            │
         ▼              ▼            ▼            ▼            ▼
┌─────────────┐  ┌───────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
│   SQLite    │  │ Subreddit │  │Analyzer │  │ChromaDB │  │  LLM    │
│  Database   │  │  Catalog  │  │ Service │  │ Vector  │  │Providers│
│ (posts,     │  │  (YAML)   │  │         │  │  Store  │  │         │
│  insights)  │  │           │  │         │  │         │  │         │
└─────────────┘  └───────────┘  └─────────┘  └─────────┘  └─────────┘
                                     │                         │
                                     └─────────────────────────┘
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                         ┌────────┐      ┌────────┐      ┌────────┐
                         │ Ollama │      │ Claude │      │ OpenAI │
                         │ (local)│      │  API   │      │  API   │
                         └────────┘      └────────┘      └────────┘

Data Flow:
1. Reddit → Collector → SQLite (posts, comments)
2. SQLite → Analyzer → LLM → SQLite (insights)
3. SQLite → Search Service → ChromaDB (embeddings)
4. User Query → ChromaDB → Semantic Results
```

---

## Business Problems & Technical Solutions

### Problem 1: Finding Startup Ideas in Reddit Noise

**Business Need**: Entrepreneurs need to find pain points, product gaps, and market signals buried in millions of Reddit posts across dozens of subreddits.

**Our Solution**:

1. **Curated Subreddit Catalog** (`backend/app/data/subreddits.yaml`)
   - Pre-selected 53 subreddits across 9 categories relevant to startup research
   - Each entry includes subscriber count, description, and "best for" guidance
   - Categories: startup, tech, product, marketing, remote work, finance, ecommerce, AI, verticals

   ```yaml
   startup_entrepreneurship:
     - name: SaaS
       subscribers: 95000
       best_for: "SaaS pain points, pricing, churn"
   ```

2. **Targeted Collection** (`backend/app/collectors/reddit.py`)
   - Uses old.reddit.com JSON endpoints (no API key required!)
   - Fetches posts sorted by "hot" (engagement signals quality)
   - Collects top comments (sorted by score = community validation)
   - Falls back to RSS or HTML scraping if rate limited

3. **Upcoming: LLM Classification** (Phase 3)
   - Will categorize posts into: pain_point, solution_request, product_mention, opportunity
   - Filters signal from noise automatically

---

### Problem 2: Privacy & Vendor Lock-in

**Business Need**: Market research data is sensitive (reveals your startup ideas). SaaS tools can shut down (GummySearch did), raise prices, or leak data.

**Our Solution**:

1. **Local-First Architecture**
   - SQLite database stored in `data/redditwatch.db`
   - No cloud dependencies for core functionality
   - All data stays on your machine

2. **Flexible LLM Provider System** (`backend/app/llm/`)

   ```
   llm/
   ├── base.py      # Abstract interface all providers implement
   ├── ollama.py    # Local LLM (default, works offline)
   ├── claude.py    # Anthropic API (optional, better quality)
   ├── openai.py    # OpenAI API (optional, alternative)
   └── factory.py   # Picks available provider with fallback chain
   ```

   **How it works**:
   - User configures preferred provider in `config.yaml`
   - Factory tries primary provider first
   - If unavailable (Ollama not running, no API key), tries fallbacks
   - All providers implement same interface, so analysis code is provider-agnostic

   ```python
   # All providers implement this interface
   class BaseLLMProvider(ABC):
       async def generate(self, prompt, system=None) -> LLMResponse
       async def generate_json(self, prompt) -> dict  # For structured extraction
       async def is_available(self) -> bool
   ```

3. **No API Keys Required for Reddit**
   - Switched from PRAW (requires OAuth) to direct HTTP requests
   - Works out of the box, no Reddit developer account needed
   - More resilient to API policy changes

---

### Problem 3: Expensive API Costs

**Business Need**: Cloud LLM APIs charge per token. Analyzing thousands of Reddit posts gets expensive fast.

**Our Solution**:

1. **Ollama as Default**
   - Free, runs locally on M1 Mac
   - llama3.1:8b is capable enough for classification/extraction
   - No API costs, no rate limits

2. **Efficient Prompts** (Phase 3)
   - Single prompt extracts multiple insights from one post
   - JSON output for reliable parsing (no re-prompting)
   - Batch processing to amortize prompt overhead

3. **Smart Collection**
   - Only fetch posts above score threshold (default: 3 upvotes)
   - Limit comments per post (top 30 by score)
   - Deduplicate on collection (don't re-fetch known posts)

---

### Problem 4: Manual Reddit Browsing is Tedious

**Business Need**: Manually reading r/SaaS, r/startups, etc. daily is time-consuming and easy to miss insights.

**Our Solution**:

1. **Automated Collection** (`backend/app/services/collector.py`)
   - Add subreddits once, collect on-demand or scheduled
   - Stores posts + comments in SQLite for later analysis
   - Tracks last collection time per subreddit

2. **Web UI for Browsing** (`frontend/index.html`)
   - Dashboard shows stats at a glance
   - Subreddits tab: browse catalog, add/remove, trigger collection
   - Posts tab: filter by subreddit, pagination, link to Reddit

3. **Upcoming: Scheduled Collection** (Phase 2.5)
   - APScheduler will run collection every 30 minutes
   - Auto-analyze new posts as they arrive

---

### Problem 5: Identifying Pain Point Severity

**Business Need**: Not all complaints are equal. "Minor annoyance" vs "I'd pay anything to fix this" require different responses.

**Our Solution** (Phase 3):

1. **Intensity Scoring** (0-100)
   - LLM analyzes emotional language, impact described, urgency
   - Higher score = more severe pain point

   ```
   Scoring factors:
   - Emotional language (frustration, anger, desperation)
   - Impact described (time wasted, money lost, blocked)
   - Urgency expressed ("need this now", "desperate")
   ```

2. **Theme Aggregation**
   - Cluster similar pain points across posts
   - Combined score = frequency × intensity (weighted)
   - Rising themes = potential opportunities

3. **Evidence Collection**
   - Store exact quotes with Reddit permalinks
   - Quote author and score (upvotes = validation)
   - Verify insights by clicking through to source

---

### Problem 6: Reddit API Lockdown (NEW)

**Business Need**: Reddit stopped approving new API applications, blocking PRAW-based collection.

**Our Solution**:

1. **old.reddit.com JSON Endpoint**
   - No authentication required
   - Full post data including scores, comments
   - `https://old.reddit.com/r/{subreddit}.json?limit=25`

2. **Fallback Chain**
   - Primary: JSON endpoint (best data)
   - Secondary: RSS feed (reliable, less data)
   - Tertiary: HTML scraping (most resilient)

3. **Rate Limit Handling**
   - 2-3 second delays between requests
   - Exponential backoff on 429 errors
   - Caching to avoid re-fetching

---

## Technical Decisions & Rationale

### Why SQLite (not Postgres)?

- **Zero configuration**: No database server to run
- **Portable**: Single file, easy to backup/move
- **Sufficient scale**: Handles 100k+ posts easily
- **FTS5 support**: Built-in full-text search for keyword queries

### Why FastAPI (not Flask/Django)?

- **Async native**: Reddit API + LLM calls benefit from async
- **Auto-documentation**: OpenAPI/Swagger UI at `/docs`
- **Pydantic integration**: Type-safe request/response models
- **Modern Python**: Type hints, async/await throughout

### Why Alpine.js (not React/Vue)?

- **No build step**: Just HTML + script tag
- **Lightweight**: 15kb minified
- **Good enough**: CRUD UI doesn't need virtual DOM
- **Fast iteration**: Edit HTML, refresh browser

### Why Direct HTTP (not PRAW)?

- **No API keys**: Works without Reddit developer account
- **Future-proof**: Less dependent on Reddit's API policies
- **Simpler setup**: No OAuth configuration needed
- **More control**: Can implement custom rate limiting and fallbacks

---

## Data Models

### Posts
```
Post
├── id (Reddit post ID, e.g., "abc123")
├── subreddit
├── title, body, author
├── score, upvote_ratio, num_comments
├── permalink (for linking back)
├── created_utc, collected_at
├── analyzed (bool)
└── category (set by LLM: pain_point, solution_request, etc.)
```

### Comments
```
Comment
├── id (Reddit comment ID)
├── post_id (FK)
├── parent_id (for threading)
├── body, author, score
└── created_utc
```

### Insights (Phase 3)
```
Insight
├── id
├── post_id, comment_id (source)
├── type (pain_point, product_mention, opportunity)
├── title, description
├── quote, quote_author, permalink
├── intensity_score (0-100)
├── product_name, sentiment (for product mentions)
└── llm_provider, llm_model (for debugging)
```

### Themes (Phase 4)
```
Theme
├── id
├── title, description, category
├── frequency (count of related insights)
├── avg_intensity
├── combined_score (frequency × intensity weighted)
├── trend (rising, stable, declining)
└── solutions (JSON, AI-generated in v1.1)
```

---

## File Structure

```
RedditWatch/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, lifespan, routes
│   │   ├── config.py            # YAML + env config loading
│   │   ├── database.py          # SQLAlchemy async setup
│   │   │
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── post.py          # + analyzed_at, analysis_duration_ms
│   │   │   ├── comment.py
│   │   │   ├── insight.py       # + theme_key for grouping
│   │   │   ├── theme.py
│   │   │   └── subreddit.py
│   │   │
│   │   ├── llm/                 # LLM provider abstraction
│   │   │   ├── base.py          # Interface + JSON parsing
│   │   │   ├── ollama.py        # Local inference (default)
│   │   │   ├── claude.py        # Anthropic API
│   │   │   ├── openai.py        # OpenAI API
│   │   │   └── factory.py       # Provider selection + fallback
│   │   │
│   │   ├── collectors/
│   │   │   └── reddit.py        # HTTP-based collection (JSON/RSS/HTML)
│   │   │
│   │   ├── services/
│   │   │   ├── collector.py     # Collection orchestration (concurrent, seed mode)
│   │   │   ├── scheduler.py     # APScheduler for automated collection
│   │   │   ├── analyzer.py      # LLM-based insight extraction
│   │   │   └── search.py        # ChromaDB semantic search
│   │   │
│   │   ├── api/                 # FastAPI route handlers
│   │   │   ├── posts.py
│   │   │   ├── subreddits.py
│   │   │   ├── collect.py       # Collection + seed endpoints
│   │   │   ├── scheduler.py     # Scheduler management endpoints
│   │   │   ├── analysis.py      # Trigger analysis, get themes/insights
│   │   │   ├── search.py        # Semantic search, similar, duplicates
│   │   │   ├── llm.py
│   │   │   └── export.py        # (Phase 6)
│   │   │
│   │   └── data/
│   │       └── subreddits.yaml  # Curated catalog (53 subreddits)
│   │
│   ├── config.yaml              # App configuration
│   └── requirements.txt
│
├── frontend/
│   └── index.html               # SPA with 6 tabs (Alpine.js + Tailwind + Chart.js)
│
├── data/
│   ├── redditwatch.db           # SQLite database (gitignored)
│   └── chroma/                  # ChromaDB vector store (gitignored)
│
├── .env                         # Secrets (gitignored)
├── .env.example                 # Template for secrets
├── .gitignore
├── project-context.md           # Full project plan
└── DEVLOG.md                    # This file
```

---

## API Reference

### Health & System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/llm/status` | GET | LLM provider availability |
| `/api/llm/test` | POST | Test LLM with prompt |

### Subreddits
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/subreddits` | GET | List monitored subreddits |
| `/api/subreddits` | POST | Add subreddit `{"name": "SaaS"}` |
| `/api/subreddits/{name}` | PUT | Toggle enable `{"enabled": false}` |
| `/api/subreddits/{name}` | DELETE | Remove from monitoring |
| `/api/subreddits/{name}/collect` | POST | Collect from one subreddit |
| `/api/subreddits/catalog` | GET | Browse curated list |
| `/api/subreddits/catalog/categories` | GET | List categories |

### Posts
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/posts` | GET | List posts (filters: subreddit, analyzed, min_score) |
| `/api/posts/stats` | GET | Aggregate statistics (includes `posts_by_date` for charts) |
| `/api/posts/{id}` | GET | Single post with comments |
| `/api/posts/{id}` | DELETE | Delete post + related data |

### Collection
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/collect` | POST | Collect from all enabled subreddits `?mode=regular|deep` |
| `/api/collect/seed` | POST | Deep scrape all subreddits (one-time initial population) |
| `/api/collect/status` | GET | Collection job status (includes scheduler state) |
| `/api/collect/test` | POST | Test Reddit connection |
| `/api/collect/refresh` | POST | Refresh comments for hot posts `?min_score=10&limit=10` |
| `/api/collect/refresh/{post_id}` | POST | Refresh comments for specific post |

### Scheduler
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scheduler/status` | GET | Show all jobs, next run times, last results |
| `/api/scheduler/start` | POST | Start the scheduler |
| `/api/scheduler/stop` | POST | Stop the scheduler |
| `/api/scheduler/trigger/{job_id}` | POST | Manually trigger a specific job |

### Analysis (Phase 3+)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | Trigger LLM analysis `?limit=10&min_score=3` |
| `/api/analyze/status` | GET | Analysis stats (posts, insights, themes, timing, `insights_by_type`) |
| `/api/analyze/themes` | GET | Aggregated themes sorted by combined score |
| `/api/analyze/insights` | GET | List insights `?type=pain_point&theme_key=...&sort=intensity` |

### Search (Phase 5)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search` | GET | Semantic search `?q=pricing%20issues&limit=20` |
| `/api/search/similar/{id}` | GET | Find similar insights `?threshold=0.7` |
| `/api/search/duplicates` | GET | Find potential duplicates `?threshold=0.9` |
| `/api/search/stats` | GET | Index statistics (indexed count, sync status) |
| `/api/search/reindex` | POST | Rebuild search index from database |

### Export (Phase 6)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/export/insights` | GET | Export insights `?format=csv|json|md&type=pain_point&theme_key=...` |
| `/api/export/insights/selected` | POST | Export specific insights `{"ids": [1,2,3]}` |
| `/api/export/insights/{id}/quote-card` | GET | Generate shareable quote card |
| `/api/export/themes` | GET | Export themes `?format=csv|json|md` |
| `/api/export/report` | GET | Generate full Markdown research report |

---

## Setup & Running

### Prerequisites
- Python 3.9+
- Ollama with llama3.1:8b pulled
- ~~Reddit API credentials~~ **NOT NEEDED ANYMORE!**

### Quick Start
```bash
# 1. Setup
cd RedditWatch
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 2. Ensure Ollama is running
ollama serve &
ollama list  # Should show llama3.1:8b

# 3. Run
cd backend
uvicorn app.main:app --reload --port 8000

# 4. Open http://localhost:8000
```

**No Reddit API keys required!** The new collector uses public endpoints.

---

## Roadmap

### ✅ Phase 1: Foundation
- [x] Project structure
- [x] Config system (YAML + env vars)
- [x] SQLite + SQLAlchemy setup
- [x] LLM provider abstraction (Ollama, Claude, OpenAI)
- [x] Basic FastAPI app

### ✅ Phase 2: Reddit Collection
- [x] ~~PRAW integration~~ → HTTP-based collection (no API key!)
- [x] Subreddit management API
- [x] Post + comment collection
- [x] Curated subreddit catalog (53 subreddits)
- [x] Web UI with tabs

### ✅ Phase 3: LLM Analysis
- [x] Conversation categorizer (pain_point, solution_request, product_mention, opportunity, general)
- [x] Pain point extractor with intensity scoring (0-100)
- [x] Product mention analyzer with sentiment
- [x] Opportunity detector
- [x] Theme key extraction for grouping
- [x] Insights API (GET /api/analyze/insights, /themes, /status)
- [x] Analysis trigger API (POST /api/analyze)

### ✅ Phase 4: Logging & Exploration UI
- [x] **Logging**: Added `analyzed_at`, `analysis_duration_ms` to Post model
- [x] **Analysis stats**: API returns timing metrics (avg duration, last analyzed)
- [x] **Insights tab**: Full UI to view extracted insights
- [x] **Themes view**: Cards showing themes sorted by combined score
- [x] **Insight type distribution**: Visual bar chart (pain points, opportunities, etc.)
- [x] **Drill-down**: Click theme → see related insights with quotes
- [x] **Recent feed**: Latest insights with type badges and intensity scores
- [x] **Filter by type**: Buttons to filter by pain_point, solution_request, etc.

### ✅ Phase 5: Validation & Search
- [x] **ChromaDB integration**: Semantic search and similarity detection
- [x] **Search bar**: Semantic search across insights in UI
- [x] **Search API**: `/api/search?q=...` with filters
- [x] **Similar insights**: `/api/search/similar/{id}` finds related insights
- [x] **Duplicate detection**: `/api/search/duplicates` finds potential duplicates
- [x] **Auto-reindex**: Insights indexed after analysis
- [x] **Evidence view**: Links back to source Reddit posts

### ✅ Phase 6: Export & Reports
- [x] **CSV export**: Bulk download of insights with filters
- [x] **JSON export**: API-friendly format with metadata
- [x] **Markdown export**: Formatted reports grouped by theme
- [x] **Full report generation**: Comprehensive Markdown report with executive summary
- [x] **Quote cards**: Shareable ASCII-art quote cards
- [x] **Filter support**: Export by type, theme, intensity range, subreddit
- [x] **UI buttons**: Export controls in Insights tab

### ✅ Phase 6.5: Data Enrichment
- [x] **Nested comment fetching**: Recursively fetch reply threads up to configurable depth (default: 5)
- [x] **Conversation refresh**: Re-fetch comments for high-engagement posts via API
- [x] **Depth tracking**: Comment model includes `depth` field (0 = top-level, 1 = reply, etc.)
- [x] **Upvotes in UI**: Display post scores with color coding, upvote ratios
- [x] **Refresh buttons**: "Refresh Hot Conversations" on Dashboard, per-post refresh in Posts tab
- [x] *Note: User karma skipped (requires separate API calls per user)*
- [x] *Note: Score snapshots for trend analysis deferred to Phase 8 (graphs)*

### ✅ Phase 7a: Large-Scale Collection
- [x] **Paginated collection** - Follow Reddit `after` cursor across multiple pages (up to 1,000 posts/sort)
- [x] **Multi-sort deep collection** - Collect from hot, new, top/week, top/month, top/year and deduplicate
- [x] **Concurrent collection** - asyncio.Semaphore-bounded parallel subreddit collection (3 concurrent)
- [x] **Seed mode** - One-time deep scrape endpoint (`POST /api/collect/seed`) for initial data population
- [x] **Selective comment fetching** - Only fetch comments for posts above `comment_min_score` threshold
- [x] **Scheduled collection** - APScheduler with regular (30min), deep (daily 3AM), and comment refresh (2hr) jobs
- [x] **Scheduler API** - Start/stop/status/trigger endpoints under `/api/scheduler`
- [x] **Rate limit hardening** - Exponential backoff on 429 errors with configurable base delay

### 🔲 Phase 7b: Performance & Polish (Deferred)
- [ ] **Background job queue** - Analysis runs async, UI shows progress
- [ ] **Cloud LLM toggle** - Option to use Claude/OpenAI for faster analysis
- [ ] **Batch prompting** - Analyze multiple posts per LLM call
- [ ] Docker Compose setup
- [ ] Error handling improvements

### ✅ Phase 8: Analytics & Visualization
- [x] **Chart.js integration**: Added Chart.js 4.4.1 CDN for visualizations
- [x] **Analytics tab**: New dedicated tab for data visualization
- [x] **Insight type distribution chart**: Doughnut chart showing pain points vs opportunities vs product mentions
- [x] **Top themes bar chart**: Horizontal bar chart of themes by combined score
- [x] **Subreddit activity chart**: Vertical bar chart of posts per subreddit
- [x] **Theme intensity scatter plot**: Bubble chart showing insight count vs avg intensity (size = count)
- [x] **Collection timeline chart**: Dual-axis line chart with daily posts and cumulative total
- [x] **Top intensity insights table**: Sortable table of highest intensity insights
- [x] **Analytics summary cards**: Total insights, active themes, avg intensity, top subreddit
- [x] **Backend updates**: Added `insights_by_type` to analysis status, `posts_by_date` to post stats

### 🔲 Phase 9: Advanced Visualizations (Future)
- [ ] **UI polish**: Better spacing, responsive design, dark/light mode toggle
- [ ] **Theme popularity timeline**: When themes spike/decline
- [ ] **Subreddit activity heatmap**: Which subreddits are most active when
- [ ] **Theme network graph**: Nodes = themes, edges = co-occurrence
- [ ] **Insight similarity graph**: Cluster similar insights visually (uses ChromaDB embeddings)
- [ ] **Subreddit × Theme matrix**: Which themes appear where
- [ ] **Product ecosystem map**: Competitive landscape from product mentions

*Note: Graph views are most valuable with ChromaDB embeddings (Phase 5) enabling similarity-based edges.*

---

## Implementation Reasoning

### Why LLM-extracted theme_key instead of free-text clustering?

**Decision**: Have the LLM output a normalized `theme_key` (e.g., "pricing_confusion") during analysis.

**Reasoning**:
1. **Deterministic grouping** - Same theme_key = same group, no fuzzy matching needed
2. **Human-readable** - Theme keys are meaningful labels, not cluster IDs
3. **LLM does the work** - The model understands context and can normalize "pricing is confusing" and "can't understand the tiers" to the same key
4. **Simpler MVP** - No embedding infrastructure needed initially
5. **Controllable** - Can provide examples in prompt to guide theme naming

**Tradeoff**: Less flexible than embedding-based clustering. Two genuinely similar pain points might get different keys if the LLM isn't consistent. We'll add ChromaDB in Phase 4 to catch these.

### Why intensity scoring (0-100)?

**Decision**: LLM assigns intensity_score based on emotional language and impact described.

**Reasoning**:
1. **Prioritization** - Not all pain points are equal. "Minor annoyance" vs "I'd pay anything to fix this"
2. **Combined scoring** - frequency × intensity surfaces high-impact, recurring themes
3. **PainOnSocial model** - Validated approach from a successful product in this space
4. **Qualitative → Quantitative** - Makes fuzzy sentiment into sortable data

**Scoring guide in prompt**:
- 0-30: Mild annoyance, "would be nice"
- 31-60: Moderate frustration, affects workflow
- 61-80: Significant pain, actively seeking solutions
- 81-100: Severe/urgent, "desperate", "blocking me"

### Why store quotes with attribution?

**Decision**: Extract verbatim quotes with author username and link to source.

**Reasoning**:
1. **Verification** - User can click through to Reddit to verify insight
2. **Evidence** - Quotes are proof, not just LLM interpretation
3. **Context** - Quote author's karma/history adds credibility signal
4. **Export value** - Quotes are useful for pitch decks, landing pages, user research docs

### Performance: Why is analysis slow?

**Observation**: ~19 seconds per post with Ollama llama3.1:8b

**Breakdown**:
- LLM inference: ~19s (main bottleneck)
- Reddit HTTP: ~1-2s
- Database: <100ms

**Root cause**: Local LLM inference is compute-intensive. llama3.1:8b processes ~30-50 tokens/second on typical hardware.

**Improvement options for future phases**:

| Approach | Speed Gain | Tradeoff |
|----------|------------|----------|
| Smaller model (llama3.2:3b) | 2-3x | Slightly lower quality |
| Cloud LLM (Claude API) | 5-10x | Costs ~$0.01/post |
| Batch prompts (5 posts/call) | 3-4x | Complex prompt engineering |
| GPU acceleration | 2-5x | Requires CUDA/Metal setup |
| Background queue | Perceived instant | Same actual time |

**Recommended approach (Phase 7)**:
1. Background job queue - user clicks Analyze, returns immediately
2. Optional cloud LLM toggle for faster analysis
3. Batch prompting for bulk operations

**Model evaluation strategy**:
1. Use large model (Claude Opus / GPT-4) to label ~100 posts as ground truth
2. Manually verify and correct the labeled data
3. Run smaller models (llama3.2:3b, mistral:7b, phi-3) on same posts
4. Compare: accuracy vs ground truth, speed, cost
5. Find optimal model for production use (best quality/speed ratio)

---

### Why batch analysis instead of real-time?

**Decision**: Analyze posts on-demand via API call, not automatically on collection.

**Reasoning**:
1. **Cost control** - LLM calls have latency and (if using cloud) cost
2. **User control** - User decides when to spend compute on analysis
3. **Debugging** - Easier to troubleshoot when collection and analysis are separate
4. **Flexibility** - Can re-analyze with different prompts without re-collecting

---

## Open Design Decisions

### Clustering & Vector DB Approach

**Problem**: How do we group similar insights into themes and deduplicate?

**Options under consideration:**

| Approach | Description | Tradeoffs |
|----------|-------------|-----------|
| **LLM-only** | Extract normalized `theme_key` during analysis, group by exact match | Simple but brittle, no semantic similarity |
| **ChromaDB** | Store embeddings via Ollama's `nomic-embed-text`, cluster by similarity | Best UX, adds dependency |
| **SQLite + embeddings** | Store embedding vectors as BLOBs, custom similarity code | No new DB, more code |
| **Hybrid** | Start with LLM theme keys, add embeddings for search later | Incremental complexity |

**Use cases enabled by embeddings:**
- "Find pain points similar to 'pricing confusion'"
- Automatic clustering of related complaints
- Deduplication: "app crashes" ≈ "keeps crashing" ≈ "unstable app"
- Semantic search across all collected data

### Logging & Observability (Phase 4 requirement)

Before building more analytics, we need better observability:

**What to log**:
- Extraction timestamp (when analysis ran)
- Processing duration per post (LLM latency)
- Token usage per analysis (cost tracking)
- Success/failure rates
- LLM provider used (for debugging quality differences)

**Why this matters**:
- Ollama on M1 Mac: ~30s per post is acceptable
- Cloud APIs: Need to track costs
- Quality debugging: "This insight seems wrong" → check which model generated it

**Implementation options**:
1. Add `analyzed_at`, `analysis_duration_ms` columns to Post model
2. Create separate `AnalysisLog` table for detailed tracking
3. Store in Insight model: `llm_latency_ms`, `token_count`

---

### Presentation & UX (Phase 5 planning)

**Key question**: How do we present insights so they're easy to consume?

**User personas**:
1. **Founder exploring ideas** - Wants to browse pain points, find opportunities
2. **Product manager** - Wants to validate specific hypotheses, export evidence
3. **Marketer** - Wants quotes for landing pages, understanding of customer language

**Presentation approaches to evaluate**:

| Approach | Pros | Cons |
|----------|------|------|
| **Theme-first** (group by theme_key) | Clear hierarchy, reduces noise | May miss cross-cutting insights |
| **Pain-first** (sorted by intensity) | Surfaces urgent problems | Can be overwhelming, no context |
| **Subreddit-first** | Good for niche research | Fragments themes across views |
| **Timeline** (recent first) | Fresh data visible | Misses recurring patterns |
| **Opportunity matrix** (frequency × intensity) | Data-driven prioritization | Requires enough data to be meaningful |

**User priority (confirmed)**: Exploration → Validation → Export

### Mode 1: Exploration (Primary)
*Goal: Browse and discover patterns*

- **Themes overview**: Cards showing top themes by combined score
- **Visual distribution**: Chart showing insight types (pain points vs opportunities vs product mentions)
- **Intensity heatmap**: Which themes have the most severe pain?
- **Recent activity**: Latest insights feed
- **Serendipity**: "Random high-intensity insight" feature

### Mode 2: Validation (Secondary)
*Goal: Test specific hypotheses*

- **Search**: Full-text search across insights and quotes
- **Filters**: By type, theme, subreddit, intensity range, date
- **Drill-down**: Click theme → see all related insights with quotes
- **Compare**: Side-by-side theme comparison
- **Evidence view**: Show source posts with Reddit links

### Mode 3: Export (Tertiary)
*Goal: Get data out for other uses*

- **Bulk export**: CSV, JSON, Markdown
- **Selective export**: Checkbox to select specific insights
- **Quote cards**: Formatted quotes for presentations
- **Report generation**: Summary with key themes and evidence

---

### Data Collection Depth & Enrichment (Open Questions)

**Date**: 2026-01-31

**Questions raised during review**:
1. How much historical data are we collecting?
2. How much can we collect?
3. Are we getting all nested comments?
4. How can we use comments to enrich analysis?
5. Are we updating existing conversations with newer data?
6. Should upvotes and karma be visible in the UI?

#### Current Collection Status

| Aspect | Current Implementation | Limitation |
|--------|----------------------|-------------|
| **Posts per collection** | 25 per subreddit (configurable) | Max 100 per Reddit API call |
| **Historical depth** | "hot" or "new" sorted posts | No deep historical backfill possible |
| **Comments** | Top 30 per post, **top-level only** | Nested reply threads are **not** fetched |
| **Score updates** | ✅ Posts get `score`/`num_comments` updated on re-collection | — |
| **Comment updates** | ❌ Only fetched for NEW posts | Existing post comments never refreshed |
| **User karma** | ❌ Not collected | Would require separate API call per user |

#### Data We Collect but Don't Surface

Currently stored but not prominently displayed in UI:
- `Post.score` (upvotes)
- `Post.upvote_ratio` (e.g., 0.92 = 92% upvoted)
- `Comment.score` (upvotes on individual comments)
- `Post.num_comments` (engagement signal)

#### Gap: Nested Comments

**Problem**: Reddit conversations often have the most valuable insights buried in reply threads. Our current collector only gets top-level comments.

**Technical reason**: Reddit's comment endpoint returns a tree structure with `replies` nested inside each comment. We currently only process the first level.

**Example of what we miss**:
```
Post: "What's the hardest part of building a SaaS?"
├── Comment A: "Marketing" (score: 45) ← WE GET THIS
│   ├── Reply A1: "Specifically, finding your first 10 customers" ← WE MISS THIS
│   └── Reply A2: "I'd pay $500/month for a tool that does this" ← VALUABLE, MISSED
├── Comment B: "Pricing" (score: 32) ← WE GET THIS
```

#### Gap: Conversation Freshness

**Problem**: High-engagement posts continue getting new comments and upvotes after initial collection. We never re-fetch this data.

**Impact**:
- Miss late replies that often contain solutions/recommendations
- Score data becomes stale (can't track engagement trends)
- No way to identify "rising" discussions

#### Options for Future Enhancement

**Option 1: Nested Comment Fetching**
```python
# Recursively process replies
def extract_comments(comment_data, depth=0, max_depth=3):
    comments = [Comment(...)]
    if depth < max_depth and 'replies' in comment_data:
        for reply in comment_data['replies']['data']['children']:
            comments.extend(extract_comments(reply['data'], depth+1))
    return comments
```
- Pros: Captures full conversations, finds buried gold
- Cons: More API calls, larger database, longer collection time

**Option 2: Conversation Refresh**
```python
# Periodically re-fetch comments for high-engagement posts
async def refresh_hot_conversations(min_score=50, max_age_days=7):
    posts = await get_posts(min_score=min_score, age_lt=7days)
    for post in posts:
        await collect_comments(post.id)  # Re-fetch all comments
```
- Pros: Keeps data fresh, catches late insights
- Cons: More API calls, need to handle comment deduplication

**Option 3: Engagement Tracking**
```python
# Store score snapshots over time
class ScoreSnapshot(Base):
    post_id: str
    score: int
    num_comments: int
    timestamp: datetime
```
- Pros: Enables trend analysis, "rising" detection
- Cons: More storage, needs scheduled job

**Option 4: Upvotes in UI**
- Show `upvote_ratio` as engagement signal on posts
- Weight quotes by comment score in theme aggregation
- Color-code insights by source engagement level
- Pros: Quick win, data already exists
- Cons: Upvotes ≠ quality (but decent proxy)

**Decision**: Skip user karma (requires per-user API calls). Consider implementing nested comments and UI enhancements in Phase 6.5 (Data Enrichment).

---

**Decision: Hybrid approach** ✅
- **Phase 3**: LLM extracts normalized `theme_key` during analysis, group by exact match
- **Phase 4**: Add ChromaDB + `nomic-embed-text` for semantic clustering/deduplication
- This lets us ship analysis quickly, then enhance with embeddings

Phase 3 implementation:
```python
# LLM outputs structured data including theme_key
{
    "type": "pain_point",
    "theme_key": "pricing_confusion",  # normalized, lowercase, underscore
    "title": "Unclear pricing tiers",
    "intensity_score": 75,
    "quote": "I spent 20 minutes trying to figure out..."
}
```

Phase 4 enhancement:
```python
# Add embeddings for similarity
import chromadb
collection.add(
    documents=[insight.description],
    ids=[insight.id],
    metadatas=[{"theme_key": insight.theme_key}]
)
# Find similar: collection.query(query_texts=["pricing issues"], n_results=10)

---

## Changelog

### 2026-01-31: Phase 8 Complete (Analytics & Visualization)
- Added **Chart.js 4.4.1** for data visualization
- Created **Analytics tab** with 5 interactive charts:
  1. **Insight Type Distribution** (doughnut): Visual breakdown of pain points, opportunities, etc.
  2. **Top Themes** (horizontal bar): Themes ranked by combined score
  3. **Subreddit Activity** (bar): Posts per subreddit comparison
  4. **Theme Intensity** (scatter/bubble): Plots themes by count vs avg intensity
  5. **Collection Timeline** (line): Daily posts + cumulative growth
- Added **analytics summary cards**: Total insights, active themes, avg intensity, top subreddit
- Added **top intensity insights table**: Sortable view of highest-intensity insights
- **Backend updates**:
  - `GET /api/analyze/status` now includes `insights_by_type` breakdown
  - `GET /api/posts/stats` now includes `posts_by_date` for timeline charts
  - `GET /api/analyze/insights` supports `sort=intensity` parameter
  - Insights response now includes `subreddit` field from joined Post
- All charts use dark theme styling to match the UI
- Charts render dynamically when Analytics tab is selected
- **Tested**: All endpoints verified working with existing data (82 insights, 73 themes, 23 posts)

### 2026-01-31: Phase 6.5 Complete (Data Enrichment)
- **Nested comment fetching**: Reddit collector now recursively extracts reply threads
  - Added `_extract_comments_recursive()` method to traverse `replies` objects
  - Configurable `max_depth` (default: 5 levels deep)
  - `include_nested` parameter to enable/disable (default: enabled)
- **Comment model updated**: Added `depth` field to track thread depth (0 = top-level)
- **Conversation refresh API**:
  - `POST /api/collect/refresh` - Refresh comments for high-engagement posts
  - `POST /api/collect/refresh/{post_id}` - Refresh specific post's comments
  - Params: `min_score`, `min_comments`, `limit`
- **Config updated**: Added `max_comment_depth` setting (default: 5)
- **UI enhancements**:
  - Posts now show color-coded scores (green 50+, yellow 10-49, gray <10)
  - Upvote ratio displayed with color coding (green 80%+, yellow 60-79%, red <60%)
  - "Refresh Hot Conversations" button on Dashboard
  - Per-post "Refresh" button in Posts tab
  - Results show new/updated comment counts
- **Tested**: Refresh found 12 new nested comments from existing posts

### 2026-01-31: Phase 6 Complete (Export & Reports)
- Created comprehensive **export API** (`api/export.py`) with:
  - `GET /api/export/insights?format=csv|json|md` - Export insights with filters
  - `GET /api/export/themes?format=csv|json|md` - Export theme summaries
  - `GET /api/export/report` - Generate full Markdown research report
  - `GET /api/export/insights/{id}/quote-card` - Shareable ASCII quote cards
  - `POST /api/export/insights/selected` - Export specific insights by ID
- **Export formats**:
  - **CSV**: Spreadsheet-ready with all fields
  - **JSON**: Includes metadata, filters applied, post titles
  - **Markdown**: Grouped by theme with quotes, type badges, intensity scores
- **Full report includes**:
  - Executive summary (posts analyzed, insights count, theme count)
  - Insight breakdown by type with emojis
  - Top 15 themes with key quotes
  - High-intensity pain points (70+) section
  - Opportunities section
  - Product mentions sentiment table
- **UI updates**: Added export buttons (CSV, JSON, Markdown) and "Generate Full Report" button to Insights tab
- Fixed SQLAlchemy lazy loading issue with `joinedload` for Post relationship

### 2026-01-31: Phase 5 Complete (Semantic Search)
- Added **ChromaDB** for vector storage and semantic search
- Created `services/search.py` with:
  - Insight embedding and indexing
  - Semantic search with filters
  - Similar insight detection
  - Duplicate finding
- Created `api/search.py` with endpoints:
  - `GET /api/search?q=...` - Semantic search
  - `GET /api/search/similar/{id}` - Find similar insights
  - `GET /api/search/duplicates` - Find potential duplicates
  - `POST /api/search/reindex` - Rebuild search index
  - `GET /api/search/stats` - Index statistics
- Added **search bar** to Insights tab in UI
- Uses ChromaDB's built-in sentence-transformers embeddings
- Auto-reindex after running analysis
- Fixed ChromaDB/numpy 2.0 compatibility (requires chromadb>=0.5.0)

### 2026-01-30: Phase 4 Complete (Logging & Exploration UI)
- Added analysis timing tracking:
  - `analyzed_at` timestamp on Post model
  - `analysis_duration_ms` per post
  - Stats API returns avg duration and last analyzed time
- Built **Insights tab** in frontend with:
  - Analysis stats cards (posts, insights, themes, avg time)
  - Top themes list sorted by combined score (frequency × intensity)
  - Insight type distribution bar chart
  - Filter buttons (pain points, solution requests, opportunities, product mentions)
  - Click theme → drill-down to related insights
  - Quote cards with author attribution and Reddit links
  - Intensity score badges (color-coded: green < 40 < yellow < 70 < red)
- Analyze button triggers LLM analysis from UI
- Analysis results show duration and extraction count

### 2026-01-30: Phase 3 Complete (LLM Analysis)

**Note: No UI at this point (prior to Phase 4)** - All testing done via curl/API calls. Web UI only has Dashboard, Subreddits, Posts tabs. Insights/Themes are API-only until Phase 5.

- Created `services/analyzer.py` for LLM-based insight extraction
- Implemented analysis prompts that extract:
  - Post category (pain_point, solution_request, product_mention, opportunity, general)
  - Theme key for grouping (e.g., "onboarding_friction", "pricing_confusion")
  - Intensity score (0-100) based on emotional language and impact
  - Verbatim quotes with author attribution
  - Product mentions with sentiment analysis
- Updated `api/analysis.py` with endpoints:
  - `POST /api/analyze` - Trigger analysis on unanalyzed posts
  - `GET /api/analyze/themes` - Get aggregated themes sorted by combined score
  - `GET /api/analyze/insights` - Get individual insights with filters
  - `GET /api/analyze/status` - Get analysis statistics
- Added `theme_key` column to Insight model
- Tested end-to-end: 23 posts → 80 insights extracted
- Top extracted themes:
  1. `onboarding_friction` (7 occurrences, combined score 41.7)
  2. `low_quality_content` (2 occurrences, intensity 71)
  3. `customer_retention` (2 occurrences, intensity 66)

### 2026-01-30: Phase 2 Testing Complete
- Successfully tested HTTP-based Reddit collection
- Added r/SaaS subreddit → fetched info (548,661 subscribers)
- Collected 23 posts and 167 comments from r/SaaS
- All endpoints verified working:
  - Health check ✅
  - Reddit connection test ✅
  - Add subreddit ✅
  - Collect posts/comments ✅
  - List posts with pagination ✅
- Removed PRAW/asyncpraw from dependencies (no longer needed)
- Updated aiosqlite to latest version (conflict was with asyncpraw)

### 2026-01-30: Reddit API Pivot
- **BREAKING**: Discovered Reddit no longer approves new API applications
- **SOLUTION**: Switched from PRAW to direct HTTP requests
- Tested three working alternatives:
  1. `old.reddit.com/r/{sub}.json` - Full JSON data, no auth needed
  2. `reddit.com/r/{sub}/.rss` - RSS feed, reliable fallback
  3. `old.reddit.com/r/{sub}/` - HTML scraping, most resilient
- Updated collector to use JSON endpoint as primary method
- Removed Reddit API key requirement from setup
- This is actually **better** - simpler setup, more resilient!

### 2026-01-30: Phase 2 Complete
- Added Reddit collector with asyncpraw
- Created curated subreddit catalog (53 subreddits in 9 categories)
- Built subreddit management API (CRUD + catalog browsing)
- Built posts API with filtering and pagination
- Updated web UI with Dashboard, Subreddits, Posts, LLM tabs
- Tested end-to-end: health, LLM status, catalog endpoints

### 2026-01-30: Phase 1 Complete
- Set up project structure
- Implemented config system with YAML + env var support
- Created SQLAlchemy models for Post, Comment, Insight, Theme, Subreddit
- Built LLM provider abstraction with Ollama, Claude, OpenAI support
- Implemented provider factory with fallback chain
- Basic FastAPI app with health and LLM test endpoints
- Verified Ollama integration working (5.2s response, JSON parsing)
