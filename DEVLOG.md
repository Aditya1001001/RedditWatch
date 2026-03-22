# RedditWatch Development Log

## Project Overview

**Goal**: Build a self-hosted alternative to GummySearch/PainOnSocial for Reddit market research.

**Why**: GummySearch shut down (Nov 2025), paid alternatives cost $20-200/month, and we want to own our data and run offline with local LLMs.

**Status**: Phase 16 in progress (Kill Intensity + Better Analysis + RAG Ask) | Phase 17 planned (Pre-Launch Dataset) | Phases 1-15 complete | SaaS launch prep underway

**Reference docs** (private, gitignored):
- `ARCHITECTURE.md` — system overview, data models, subsystem descriptions
- `TECHNICAL_DECISIONS.md` — rationale for stack/design choices

---

## Pending Work

### Phase 16: Better Analysis + RAG Ask

Three changes this round (items #4 smart suggestions and #5 audience templates deferred — templates will be hand-curated via one-time Claude task, no pipeline):

**1. Kill intensity score from UI, sort by engagement**

The LLM-assigned 0-100 intensity number is opaque guesswork. Reddit's own engagement signals (upvotes, comments) are real community validation.

- Frontend: Replace intensity score display on insight cards with post engagement (pts + comments)
- Frontend: Remove `total_score` (intensity-based) from theme patterns panel, replace with count-based sort
- Backend `services/analyzer.py`: Change default sort in `get_insights_by_theme()` from `Insight.intensity_score.desc()` to `Post.score.desc()`
- Keep `intensity_score` column in DB — costs nothing, useful as future clustering input

Files: `frontend/index.html`, `backend/app/api/analysis.py`, `backend/app/services/analyzer.py`

**2. Better post analysis**

More context to the LLM, better prompt, quote validation.

- Increase post body from `post.body[:2000]` → `post.body[:4000]`
- Increase comment limit from 10 → 15, comment body from 500 → 800 chars
- Add reply threads: for top comments with score > 5, fetch top 1 reply per parent
- Add post metadata block to prompt: score, num_comments, upvote_ratio
- Replace `ANALYSIS_SYSTEM_PROMPT` with evidence-focused version
- Add quote validation via `difflib.SequenceMatcher` (ratio > 0.7 or set `quote = None`)

File: `backend/app/services/analyzer.py`

**3. RAG-enhanced Ask + multi-turn**

Ask currently sends almost no real content to the LLM — just summary stats and 5 sample insight titles. Need actual insight content via ChromaDB retrieval.

- Query ChromaDB for 12 most relevant insights, post-filter to audience subreddits
- Rich prompt with audience context, data overview, type/theme summaries, and retrieved insights
- Better system prompt: cite specific insights/quotes/subreddits, give actionable recommendations
- Increase `max_tokens` from 1024 → 2048
- Add `history` to `AskRequest` for multi-turn context
- Frontend: send `history: this.queryHistory.slice(0, 3)` in ask request body

Files: `backend/app/api/audiences.py`, `frontend/index.html`

**Verification checklist**:
- [ ] No intensity score visible anywhere in UI. Insights sorted by post upvotes
- [ ] Post engagement shown on insight cards (pts + comments)
- [ ] Better analysis: re-analyze posts → insights have reply context, no fabricated quotes
- [ ] Ask quality: ask "What frustrations do people have?" → response cites specific quotes and subreddits
- [ ] Multi-turn: ask follow-up → references previous answer

### Phase 11: Reddit OAuth (Deferred)

**Rate limiter**: Done — global token-bucket rate limiter, exponential backoff, concurrent task throttling all implemented.

**OAuth**: Deferred until throughput becomes a bottleneck. Currently operating at ~10 req/min (unauthenticated). OAuth would give 100 req/min. Not needed yet.

Remaining OAuth tasks when needed:
- [ ] Register Reddit "script" app at reddit.com/prefs/apps
- [ ] Implement OAuth client credentials flow
- [ ] Switch endpoints from `old.reddit.com/*.json` to `oauth.reddit.com/r/*`
- [ ] Parse `X-RateLimit-*` response headers for precise throttling

### Phase 13: Native Mac App (Deferred — Post-Launch)

Goal was to package as native macOS app (menu bar, background collection, `.dmg` distribution). **Deferred to v2** — focusing on web SaaS first. Plan preserved for reference:
- Options: Tauri (sidecar), PyWebView (pure Python), Swift + WKWebView
- Features: menu bar status, background collection, native notifications, launch at login

### Other Pending Items

- [ ] Take fresh screenshots after Phase 16 UI changes
- [ ] Remaining codebase audit items (~15 unfixed, mostly architectural — see audit summary below)
- [x] Insight list pagination (default 10, user-selectable up to 50)

### Phase 17: Pre-Launch Dataset — Collection + Analysis

Ship RedditWatch with a pre-loaded, already-analyzed dataset that serves two purposes:
1. **Demo data** — new users see a populated dashboard with real insights on signup
2. **Content marketing** — use the analyzed data to write blog posts, tweets, and landing page copy

Timeline: this week. Approach: lean (37 curated subs, not 100+).

**Step 1: Make OpenAI provider URL-configurable (for Groq)**

Problem: `OpenAIProvider` has hardcoded `API_URL` and `is_available()` requires key starting with `sk-`. Groq uses a different URL and key prefix (`gsk_`).

Solution: Make the OpenAI provider generic enough to work with any OpenAI-compatible API.

Files to modify:
- `backend/app/config.py` — add `base_url` field to `OpenAIConfig` (default: `https://api.openai.com/v1`)
- `backend/app/llm/openai.py` — use config `base_url` instead of hardcoded URL; relax the `sk-` check in `is_available()`

Users configure Groq by setting:
```yaml
llm:
  provider: openai
  openai:
    base_url: "https://api.groq.com/openai/v1"
    model: "llama-3.3-70b-versatile"
```
And `OPENAI_API_KEY=gsk_...` in `.env`.

**Step 2: Collect data from 37 subreddits**

No code changes — use existing deep collect via API.

Tier 1 — Core Demo (15): SaaS, startups, Entrepreneur, indiehackers, microsaas, SideProject, smallbusiness, marketing, SEO, ecommerce, shopify, sales, freelance, ProductManagement, nocode

Tier 2 — Content-Worthy Niches (10): selfhosted, ChatGPT, recruitinghell, personalfinance, cscareerquestions, digitalnomad, Etsy, Teachers, YNAB, LocalLLaMA

Tier 3 — Breadth (12): webdev, devops, aws, emailmarketing, dropship, CryptoCurrency, realestateinvesting, 3Dprinting, podcasting, privacy, homelab, GrowthHacking

Execution:
1. Add all 37 subs to monitoring: `POST /api/subreddits {"name": "..."}` for each
2. Trigger deep collection: `POST /api/collect/seed`
3. Wait ~5-6 hours at 8 RPM

Expected yield: ~37K posts, ~100K comments

**Step 3: Analyze with Groq**

1. Set up Groq: create account at console.groq.com, get API key
2. Configure `.env` + `config.yaml` per Step 1
3. Trigger analysis: `POST /api/analyze?limit=50&min_score=3` (repeat until all analyzed)

Expected: ~24K posts to analyze (score >= 3), ~$2-5 on Groq paid, done in 2-3 hours.

**Step 4: Consolidate themes**

After analysis: `POST /api/analyze/themes/consolidate`

**Verification checklist**:
- [ ] Groq integration works: set config, hit `/api/llm/test`, get response
- [ ] All 37 subs collected with deep data
- [ ] Analysis complete: `/api/analyze/status` shows 0 unanalyzed posts (with score >= 3)
- [ ] Themes consolidated: no obvious duplicates in `/api/analyze/themes`
- [ ] Demo looks good: open UI, select an audience with these subs, insights are populated and useful

### Priority Order (Agreed 2026-03-21)

1. **Phase 16 #1, #2, #3** — Kill intensity + better analysis + RAG Ask
2. **Dedicated test pass** — Core loop coverage (collection + analysis)
3. **Auth** — Accounts, login
4. **Billing** — Stripe India integration
5. **Deployment plan** — Host the SaaS version
6. Hand-curate audience templates (one-time Claude task)
7. Everything else is post-launch

---

## Codebase Audit Summary

Full audit conducted 2026-03-16. Two hardening passes completed (27 of ~60 items fixed).

**Fixed (27 items across 2 passes):**
- N+1 queries (search API, subreddit growth)
- Composite indexes: (analyzed, created_utc), (subreddit, analyzed), comment_id, theme_id
- Broad exception handling in analyzer
- Post body truncation indicator
- Case sensitivity in subreddit growth endpoint
- Session commit error logging
- ChromaDB search timeout (30s, returns 504)
- Race condition on audience switching (AbortController)
- Error toast duration (8s for errors)
- Modal focus trap + Escape
- Loading skeletons for insights/posts
- Silent API failure toasts (loadAudiences, loadAnalyticsData, etc.)
- Task polling timeout

**Partially fixed (7):** composite indexes (2/3 done), eager loading, pagination, silent failures (most done), input validation, chart leaks, accessibility

**Not fixed (15, mostly architectural/low-impact):**
- InsightTheme index, partial index for `analyzed=False`
- `getAudienceGrowth()` 3x call per render
- Monolithic HTML file (~2300 lines)
- Magic numbers / hardcoded limits
- LLM startup validation
- Duplicate error handling patterns

---

## Billing Plan (2026-03-19)

**Stripe India** for payment processing. Sole proprietorship + GST sufficient.

Flow: Landing page → Stripe Checkout Session → webhook `checkout.session.completed` → create/upgrade user account → backend checks subscription status.

Implementation pieces:
- [ ] Sign up for Stripe India with PAN + GST
- [ ] Create Products + Prices in Stripe Dashboard
- [ ] `/api/billing` module — checkout session creation, webhook handling
- [ ] `subscriptions` table (user email ↔ Stripe Customer ID ↔ status)
- [ ] Feature gating based on subscription status

---

## Changelog

### 2026-03-22: Design Polish — Insight Cards + Type Overview

Visual hierarchy and color personality for the two primary data surfaces. Addresses three user issues: walls of text, no visual hierarchy, flat dark-on-dark appearance.

**6 changes shipped:**

1. **Colored left borders on insight cards** — 3px left border in insight type color (pain=red, solution=green, etc.) + `bg-surface-1` lift + increased card spacing
2. **Redesigned type overview cards** — colored top accent bar replaces dot, hero count number in type color replaces small gray pill, empty types dimmed to `opacity-50`
3. **Elevated quote block** — warm amber background tint (`bg-accent/[0.04]`), Newsreader serif font at 15px, brighter text, larger quote marks — the "found gold" moment
4. **Stronger title/description hierarchy** — title bumped to `font-semibold text-text-primary`, description dropped to `text-[13px] text-text-muted`
5. **Better engagement stats** — SVG icons (upvote arrow, chat bubble) replace "pts"/"comments" text labels, bumped to `text-text-secondary`
6. **Cleaner footer** — removed border separator, theme key styled as chip, link fades until hovered, renamed "View on Reddit" → "View source"

**Bonus: Insight list limit selector** — default reduced from 50 → 10, dropdown (10/25/50) next to insight count header. Resolves the "hard-capped at 50" pending item.

Files: `frontend/index.html` only — HTML/CSS, no JS logic or backend changes.

### 2026-03-22: New Post Tracking + Young Post Refresh

Regular collection was only fetching "hot" — new posts were invisible until they gained traction or the daily 3 AM deep collection ran. Posts also never got their `upvote_ratio` updated on re-collection, and `score`/`num_comments` only updated if the post happened to reappear.

**6 changes shipped:**

1. **Fix `upvote_ratio` update** — one-line fix in `_save_posts_to_db()`, was silently dropped on re-collection
2. **Multi-sort regular collection** — `collect_subreddit()` now fetches both "hot" and "new" (configurable via `regular_sort_modes`), deduplicates by post ID
3. **`fetch_posts_by_id()`** — new method on `RedditCollector` using Reddit's `/by_id/t3_id1,t3_id2,...` endpoint, fetches fresh metadata for up to 100 posts per API call
4. **`refresh_young_posts()`** — queries posts < 5 days old, batch-updates `score`/`num_comments`/`upvote_ratio`, refreshes comments for top 5 growing posts
5. **4th scheduler job** — `young_post_refresh` runs every 4 hours (configurable)
6. **Comment refresh metadata update** — `refresh_hot_conversations()` now also batch-updates post metadata after refreshing comments (1 extra API call)

API budget: ~525/day → ~819/day (7.1% of 11,520 capacity at 8 RPM). All config fields have defaults — no yaml changes required.

Files: `collector.py`, `reddit.py`, `scheduler.py`, `config.py` — no new files, no schema changes, no frontend changes.

### 2026-03-21: UX Simplification — Reduce Noise, Surface Value

Designer feedback: "reduce and simplify." 18+ data sections across 9 navigation surfaces was too much noise. Core loop: pick audience → see insights → drill down → act.

**Landing page: 3 tabs → 2 tabs**
- "Saved" → "Audiences", "Curated" + "Trending" merged into "Discover"
- 3 trending tables replaced with 1 sortable table (clickable column headers)

**Audience view: 6 tabs → single scrollable page**
- Removed tab bar (was: Themes, Ask, Subreddits, Topics, Posts, Analytics)
- Unified Search/Ask input with mode toggle
- Insight type cards in responsive grid
- Topics, Trends, Raw Posts as collapsible disclosure sections
- Removed: Analytics tab (heatmap, matrix, intensity table cut; trends chart kept in collapsible)

**Result**: ~2900 → ~2300 lines (~600 lines cut). 9 navigation surfaces → 4.

### 2026-03-20: Audit Hardening Pass #2 — 11 Fixes

Backend: session commit logging, ChromaDB timeout, case normalization.
Frontend: AbortController race fix, error toast duration, modal focus trap + Escape, loading skeletons, silent failure toasts.

### 2026-03-20: Subreddit Discovery — Search API + Community Scraper

- `RedditCollector.search_subreddits()` hits `/subreddits/search.json`
- Audience form: search-as-you-type with 300ms debounce, removable pills, catalog suggestions
- Community directory scraper (`scripts/private/scrape_popular.py`): 225,905 subreddits scraped
- Also: audience "ask" endpoint, theme consolidation endpoint, insight post metadata enrichment

### 2026-03-19: Smart Startup Collection

Auto-collect stale data on app startup (>12hr threshold, configurable). Non-blocking background task with progress banner.

### 2026-03-16: Catalog Rebuild — 287 → 46 Categories, 1,859 → 263 Curated Subs

Clean display names, category pills with counts, cards with descriptions.

### 2026-03-16: Private Monorepo + Public OSS Mirror

Private `redditwatch-pro` repo → auto-synced public `RedditWatch` mirror via GitHub Actions. `.oss-ignore` strips SaaS-only paths. `EDITION` env var toggles cloud features.

### 2026-03-16: Phase 9 — Advanced Visualizations

Theme timeline, activity heatmap, co-occurrence network (D3.js), subreddit × theme matrix. Plus N+1 fixes and composite indexes.

### 2026-03-16: Codebase Audit

Full audit: 60+ issues across backend/frontend. See audit summary section above.

### 2026-03-14: Phase 10 — Historical Data & UI Polish

- Audiences (multi-subreddit groups) + CRUD API
- Subreddit growth tracking (SubscriberSnapshot time-series)
- Arctic Shift researched for historical backfill (deferred)
- Full visual overhaul: Plus Jakarta Sans, warm color palette, toast system, accessibility
- Bumped to v0.2

### 2026-02-13: Large-Scale Collection (Phases 7a)

Paginated multi-sort collection (1,000+ posts/sub), concurrent collection, seed mode, scheduled collection (APScheduler), selective comment fetching.

### 2026-02-13: Phases 0-4 Complete

Phase 0: Git hygiene. Phase 1: Security fixes (CORS, background tasks, LLM validation, rate limits, O(N^2) fix). Phase 2: Input validation, ChromaDB sync. Phase 3: 48 tests, CI. Phase 4: MIT License, Docker, README, CONTRIBUTING.md.

### 2026-01-31: Phases 5-8 Complete

Phase 5: ChromaDB semantic search. Phase 6: Export (CSV/JSON/MD/report). Phase 6.5: Nested comment fetching, conversation refresh. Phase 8: Analytics tab (Chart.js, 5 chart types).

### 2026-01-30: Phases 1-4 Complete

LLM analysis pipeline, insights UI, theme extraction, export system. Reddit API pivot from PRAW to direct HTTP (Reddit stopped approving new apps).

---

## Roadmap

### ✅ Phase 1: Foundation
### ✅ Phase 2: Reddit Collection (HTTP-based, no API key)
### ✅ Phase 3: LLM Analysis
### ✅ Phase 4: Logging & Exploration UI
### ✅ Phase 5: Semantic Search (ChromaDB)
### ✅ Phase 6: Export & Reports
### ✅ Phase 6.5: Data Enrichment (nested comments, conversation refresh)
### ✅ Phase 7a: Large-Scale Collection (pagination, concurrency, scheduler)
### ✅ Phase 8: Analytics & Visualization (Chart.js)
### ✅ Phase 9: Advanced Visualizations (timeline, heatmap, network, matrix)
### ✅ Phase 10: Audiences, Growth Tracking, UI Polish
### ⏸️ Phase 11: Reddit OAuth (rate limiter done, OAuth deferred)
### ✅ Phase 12: UI/UX Audit (reconciled — 8/20 items done by UX simplification, 4 survivors folded into Phase 16, rest N/A)
### ⏸️ Phase 13: Native Mac App (deferred post-launch)
### ✅ Phase 14: Subreddit Discovery + Community Scraper
### ✅ Phase 15: UX Simplification (9 surfaces → 4)
### 🔲 Phase 16: Kill Intensity + Better Analysis + RAG Ask (in progress)
### 🔲 Phase 17: Pre-Launch Dataset — Collection + Analysis (planned)

### 🔲 Phase 7b: Performance & Polish (Deferred)
- [ ] Cloud LLM toggle for faster analysis
- [ ] Batch prompting (multiple posts per LLM call)
- [ ] Docker Compose setup
