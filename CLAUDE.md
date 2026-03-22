## Versioning

Single source of truth: `backend/app/__init__.py` (`__version__`). Imported by `main.py` — never hardcode version strings elsewhere.

**Pre-1.0 convention:**
- **Patch** (0.2.X) — bug fixes, design tweaks, config changes, data collection
- **Minor** (0.X.0) — new features, new API endpoints, data model changes

Bump the version in the same commit as the feature/fix it corresponds to.

---

## Design Context

### Users
Solo founders and small-team operators doing market research. They come to RedditWatch to find patterns in Reddit discussions — pain points, product mentions, opportunities — that inform product and GTM decisions. They're technical enough to self-host but want the tool to do the heavy lifting on analysis.

### Brand Personality
**Calm, insightful, credible.** The UI is the quiet counterweight to noisy Reddit data. It should feel like a research companion, not a dashboard.

### Emotional Goal
**"I found gold."** The primary emotion is discovery — surfacing hidden patterns and real voices that competitors miss. Moments when a quote or theme clicks should feel rewarding.

### Aesthetic Direction
- **Base:** Clean and calm. Low cognitive load, generous whitespace, content breathes.
- **Accent:** Warm amber (#d4a373) — earthy, approachable, not corporate.
- **Typography:** Plus Jakarta Sans (UI), Newsreader serif (quotes/editorial moments).
- **Theme:** Dark mode only. Surfaces: warm charcoal (#111110 → #363630). Text: warm off-whites.
- **References:** Linear (minimal, fast, intentional), Superhuman (premium dark, confident type).

### Anti-References
- Generic Bootstrap/Material admin dashboards
- Cluttered analytics tools (Google Analytics, Mixpanel)
- Playful/consumer apps with illustrations or mascots
- Enterprise/corporate bloat (Salesforce)

### Design Principles
1. **Content over chrome** — The insights, quotes, and patterns are the product. UI should frame them, not compete.
2. **Calm structure, rewarding details** — Layout is predictable and scannable; delight lives in the content (a great quote, a surprising theme).
3. **Ground in evidence** — Always show the source: the subreddit, the quote, the author. Credibility comes from specificity.
4. **Density when earned** — Start sparse, allow density as users dig deeper. Never overwhelm on first glance.
5. **Warm, not cold** — Earthy tones, serif quotes, human language. This is about people's real words, not abstract metrics.
