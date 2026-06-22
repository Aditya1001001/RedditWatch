# RedditWatch Improvement Roadmap

This roadmap turns the product and engineering audit into an incremental path toward a portfolio-grade project. The goal is not a rewrite. The goal is to make RedditWatch demonstrate product taste, engineering judgment, and the ability to ship a useful, credible tool.

## Phase 1: Stabilize

### Goal

Make the current app reliable enough that a first user can complete the core loop without silent failure.

### Exact Improvements

- Align default LLM config and docs so local setup works predictably.
- Make collection preconditions explicit: collection runs against followed audiences.
- Add clear failures for no followed audiences, no monitored subreddits, no Reddit data, LLM unavailable, and stale search index.
- Stop marking failed analysis as successfully analyzed; preserve retryability.
- Sanitize rendered AI Markdown before inserting it into the browser DOM.
- Expose search index health and an obvious reindex action.
- Confirm scheduler and startup collection behavior is documented.

### Suggested Commit Order

1. `fix: align llm defaults with local setup`
2. `fix: explain and validate followed audience collection`
3. `fix: preserve retryability for failed analysis`
4. `fix: sanitize ai answer rendering`
5. `fix: surface search index health and reindex state`

### Files Likely Involved

- `backend/config.yaml`
- `backend/app/config.py`
- `backend/app/database.py`
- `backend/app/models/post.py`
- `backend/app/services/collector.py`
- `backend/app/services/analyzer.py`
- `backend/app/api/collect.py`
- `backend/app/api/analysis.py`
- `backend/app/api/search.py`
- `backend/app/services/search.py`
- `frontend/index.html`
- `README.md`

### How To Test

- Run `python -m pytest tests/ -v` from `backend`.
- Manual smoke test: create audience, add 1-2 subreddits, follow audience, collect, analyze, search, ask, export.
- Test LLM unavailable path with no Ollama/API key.
- Test no followed audiences path.
- Test reindex after deleting/recreating insights.

### What Not To Do Yet

- Do not redesign the UI.
- Do not add more insight categories.
- Do not introduce a frontend build system.
- Do not rewrite storage or background task execution.

### Definition Of Done

- A new user cannot silently get zero collected posts without explanation.
- Failed analysis can be retried.
- AI-rendered content is sanitized.
- README setup matches actual defaults.
- The core smoke flow works consistently.

## Phase 2: Clarify The Product

### Goal

Make the core user, value proposition, onboarding, and "aha" moment obvious in the app itself.

### Exact Improvements

- Define the primary user clearly: founder, product, marketing, or research user monitoring Reddit audiences.
- Rename or explain key concepts: Audience, Follow, Collect, Analyze, Insights.
- Add a first-use path: create audience, collect conversations, analyze, review evidence, export report.
- Add an empty-state call to action that creates a sample audience or sends users to curated subreddit categories.
- Add an in-app research-loop status panel showing setup progress.
- Make the aha moment prominent: top pain points, top quotes, opportunity themes, and product mentions.

### Suggested Commit Order

1. `product: clarify first-run research workflow`
2. `product: improve audience and collection copy`
3. `product: add insight-focused overview for selected audience`
4. `product: add sample starter audience path`

### Files Likely Involved

- `frontend/index.html`
- `backend/app/data/subreddits.yaml`
- `backend/app/api/audiences.py`
- `README.md`
- `project-context.md`

### How To Test

- Start with an empty local database.
- Verify the first screen tells the user what to do.
- Complete the flow without reading the README.
- Confirm the app can be explained from the UI in under 10 seconds.

### What Not To Do Yet

- Do not add a marketing landing page.
- Do not add auth or multi-user concepts.
- Do not overbuild onboarding tours.

### Definition Of Done

- First-time users know what to do next.
- Followed-audience collection behavior is understandable.
- The app leads toward evidence-backed insights, not raw dashboard metrics.

## Phase 3: Improve The Insight Engine

### Goal

Make insights more credible, useful, and product-relevant.

### Exact Improvements

- Improve fetch prioritization using score, comments, recency, subreddit type, and discussion richness.
- Add post filtering before LLM analysis for obvious spam, low-signal self-promotion, announcements, deleted content, and empty content.
- Store why a post was skipped or analyzed.
- Improve prompt evaluation with fixed Reddit fixtures and expected outputs.
- Strengthen product mention extraction with product name, sentiment, reason, competitor context, and pricing or budget signals.
- Add stronger quote provenance: post/comment source, author, score, and permalink where possible.
- Improve theme consolidation with safer, reviewable merges.
- Add research-summary generation from top themes and quotes.

### Suggested Commit Order

1. `engine: add signal scoring for collected posts`
2. `engine: skip low-signal posts with explicit reasons`
3. `engine: improve product mention schema`
4. `engine: add prompt fixture evaluation tests`
5. `engine: strengthen quote provenance`
6. `engine: improve theme consolidation safety`

### Files Likely Involved

- `backend/app/services/collector.py`
- `backend/app/collectors/reddit.py`
- `backend/app/services/analyzer.py`
- `backend/app/models/post.py`
- `backend/app/models/comment.py`
- `backend/app/models/insight.py`
- `backend/app/api/analysis.py`
- `backend/app/api/export.py`
- `backend/tests/test_services/`

### How To Test

- Add unit tests for Reddit parsing edge cases.
- Add fixture tests for LLM JSON validation and classifications.
- Add regression tests for self-promotional posts.
- Manually check exported reports: every major claim should have evidence.

### What Not To Do Yet

- Do not build autonomous strategy recommendations.
- Do not scrape aggressively across every possible Reddit page.
- Do not add many new categories unless they improve research decisions.

### Definition Of Done

- Low-signal content is filtered.
- Insights feel specific and grounded.
- Product mentions become useful competitive intelligence.
- Prompt changes are testable against fixtures.

## Phase 4: Improve UX Polish

### Goal

Make the app feel calm, intentional, and demo-ready.

### Exact Improvements

- Improve visual hierarchy around the selected audience overview.
- Make insight cards more scannable: type, theme, quote, source, and engagement.
- Add better loading states for collection, analysis, search, Q&A, and report export.
- Improve empty states with exact next actions.
- Add success states after collection and analysis with useful counts.
- Add a demo mode or sample data banner.
- Improve mobile layout enough for portfolio screenshots.
- Clean up wording: fewer generic labels, more research-oriented copy.

### Suggested Commit Order

1. `ux: improve audience overview hierarchy`
2. `ux: refine insight cards and source evidence`
3. `ux: add actionable empty and error states`
4. `ux: improve task progress and completion states`
5. `ux: polish demo and screenshot flow`

### Files Likely Involved

- `frontend/index.html`
- `screenshots/`

### How To Test

- Manual pass at desktop and mobile widths.
- Test empty database, partial database, and populated database states.
- Test slow network and LLM unavailable scenarios.
- Screenshot the intended portfolio flow.

### What Not To Do Yet

- Do not chase animation-heavy polish.
- Do not introduce a design system library.
- Do not split the frontend just for aesthetics.

### Definition Of Done

- The first screen, audience page, and insight cards look portfolio-grade.
- Every empty, loading, and error state tells the user what is happening.
- Screenshots clearly communicate the product.

## Phase 5: Improve Engineering Quality

### Goal

Reduce maintenance risk without changing the product shape.

### Exact Improvements

- Split the large frontend file only where it reduces complexity: app state/actions, styles, and markup sections.
- Add focused service tests for collector, analyzer, search, exports, and audience scoping.
- Add integration tests for collect to analyze to insights with mocked Reddit and LLM providers.
- Replace ad hoc schema changes with a simple migration strategy.
- Improve typing around API schemas and service return objects.
- Reduce duplicated frontend polling/task handling.
- Add lightweight lint and format commands if useful.

### Suggested Commit Order

1. `test: cover collection dedupe and audience scoping`
2. `test: cover analyzer failure and retry behavior`
3. `test: cover export and search indexing`
4. `refactor: extract frontend app logic`
5. `refactor: centralize task polling`
6. `chore: add migration structure`
7. `chore: add lint and formatting workflow`

### Files Likely Involved

- `frontend/index.html`
- `frontend/app.js`
- `backend/app/services/tasks.py`
- `backend/app/database.py`
- `backend/tests/`
- `.github/workflows/test.yml`
- `backend/pyproject.toml`

### How To Test

- Run the full backend test suite.
- Confirm coverage hits core service paths, not just empty endpoints.
- Manual smoke test after frontend extraction.
- Run CI matrix locally where practical.

### What Not To Do Yet

- Do not move to React or Vite just because the file is large.
- Do not introduce Celery or Redis unless task reliability becomes a real need.
- Do not replace SQLite.

### Definition Of Done

- Core behavior has meaningful tests.
- Frontend is easier to navigate.
- Schema upgrades are explicit.
- Refactors do not change product behavior.

## Phase 6: Portfolio Packaging

### Goal

Make the project easy to understand, run, evaluate, and discuss.

### Exact Improvements

- Rewrite README around the real demo path.
- Add "Why this exists", "Who it is for", "Product decisions", and "Architecture" sections.
- Add a sample dataset or demo seed script.
- Add current screenshots and GIFs from the polished flow.
- Add an architecture diagram and data flow: Reddit to SQLite to LLM to insights to Chroma to search/Q&A/export.
- Add setup paths for Docker, local install, Ollama, and cloud LLMs.
- Add security and privacy notes: local-first, no auth, do not expose publicly as-is.
- Add known limitations and future roadmap.
- Add portfolio notes explaining tradeoffs and product judgment.

### Suggested Commit Order

1. `docs: add demo seed workflow`
2. `docs: rewrite readme around product flow`
3. `docs: add architecture and product notes`
4. `docs: refresh screenshots and gifs`
5. `docs: add limitations and roadmap`

### Files Likely Involved

- `README.md`
- `CONTRIBUTING.md`
- `project-context.md`
- `screenshots/`
- `scripts/`
- `docs/architecture.md`
- `docs/product-notes.md`

### How To Test

- Fresh clone test.
- Docker startup test.
- Local setup test.
- Demo data load test.
- Ask someone to follow README without help.

### What Not To Do Yet

- Do not over-market with vague claims.
- Do not hide limitations.
- Do not add cloud/SaaS positioning unless it is actually supported.

### Definition Of Done

- A portfolio reviewer can understand the product in under a minute.
- They can run or inspect a demo without live Reddit or LLM dependency.
- README reflects the actual app.
- The project communicates product thinking and engineering judgment.
