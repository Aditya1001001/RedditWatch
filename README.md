# RedditWatch

[![Tests](https://github.com/Aditya1001001/RedditWatch/actions/workflows/test.yml/badge.svg)](https://github.com/Aditya1001001/RedditWatch/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Market research from Reddit, on your terms.**

A self-hosted, LLM-powered tool that discovers pain points, product opportunities, and market signals from Reddit discussions. No Reddit API key needed. No monthly fees. Your data stays on your machine.

> GummySearch shut down in December 2025 after Reddit killed their API access. RedditWatch uses public endpoints (old.reddit.com) — it can't be shut down the same way. Free forever, open source.

![RedditWatch Dashboard](screenshots/v0.3/dashboard.png)

## Why RedditWatch?

- **No Reddit API key required** — Uses public old.reddit.com endpoints. Immune to API policy changes.
- **Free and open source** — Self-host it. No subscriptions, no vendor lock-in.
- **LLM-powered analysis** — Not just keyword alerts. Extracts pain points, solution requests, product mentions, and opportunities with intensity scoring.
- **Works with free local models** — Defaults to Ollama (llama3.1:8b). Zero cost, fully private. Also supports Claude and OpenAI.
- **Semantic search** — Find related insights by meaning using ChromaDB embeddings.
- **Export everything** — CSV, JSON, Markdown, or full research reports.

## See It in Action

### Insights — Themes, Semantic Search, and Exports

![Insights](screenshots/v0.3/insights.gif)

### Analytics — Charts, Trends, and High-Intensity Signals

![Analytics](screenshots/v0.3/analytics.gif)

### Subreddit Catalog — 117 Curated Subreddits Across 20 Categories

![Subreddits](screenshots/v0.3/subreddits.png)

### LLM Provider Management

![LLM Providers](screenshots/v0.3/llm.png)

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/Aditya1001001/RedditWatch.git
cd RedditWatch
cp .env.example .env
docker compose up
```

Open http://localhost:8000

**With local LLM (Ollama):**

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up
```

### Option 2: Local Install

```bash
git clone https://github.com/Aditya1001001/RedditWatch.git
cd RedditWatch
./scripts/setup.sh
./scripts/run.sh
```

### Prerequisites (Local)

- Python 3.9+
- [Ollama](https://ollama.ai) with `llama3.1:8b` model (or Claude/OpenAI API key)

```bash
# Install Ollama and pull a model
ollama pull llama3.1:8b
```

## How It Works

### 1. Add Subreddits

Go to the **Subreddits** tab. Type a subreddit name or browse the curated catalog of 117 subreddits across 20 categories (startups, tech, marketing, cybersecurity, gaming, health, education, and more). When creating audience groups, the app suggests related subreddits from the same category.

### 2. Collect Posts

Click **Collect All Posts** on the Dashboard. RedditWatch scrapes posts and comments from old.reddit.com in the background — no API key, no rate limit worries.

### 3. Analyze with LLM

Go to the **Insights** tab and click **Analyze Posts**. The LLM reads each post and its comments, then extracts:
- **Pain Points** — User frustrations with intensity scores (0-100)
- **Solution Requests** — "I wish there was a tool that..."
- **Product Mentions** — Tools/services discussed, with sentiment
- **Opportunities** — Market gaps and unmet needs

### 4. Explore & Export

- **Themes** — Pain points grouped by theme (e.g., "onboarding_friction"), ranked by frequency x intensity
- **Semantic Search** — Find insights by meaning, not just keywords
- **Analytics** — Insight distribution, top themes, intensity scatter plots, collection timeline
- **Export** — CSV, JSON, Markdown, or generate a full research report

## Configuration

RedditWatch works out of the box with Ollama. All settings are optional.

Copy `.env.example` to `.env` for cloud LLM providers:

```bash
# Optional: For Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Optional: For OpenAI API
OPENAI_API_KEY=sk-...
```

Edit `backend/config.yaml` to customize:

```yaml
llm:
  provider: ollama  # or "claude" or "openai"

collection:
  posts_per_subreddit: 25
  include_comments: true

server:
  cors:
    allowed_origins:
      - "http://localhost:8000"
```

## API

42+ endpoints across 9 modules. Full interactive docs at http://localhost:8000/docs

| Module | Prefix | Key Endpoints |
|--------|--------|---------------|
| Health | `/api/health` | Health check |
| Posts | `/api/posts` | List, get, delete, stats |
| Subreddits | `/api/subreddits` | CRUD, catalog, collect per-sub |
| Collection | `/api/collect` | Trigger collection, status, refresh comments |
| Analysis | `/api/analyze` | Trigger analysis, themes, insights, status |
| Search | `/api/search` | Semantic search, similar, duplicates |
| Export | `/api/export` | CSV/JSON/Markdown export, reports, quote cards |
| LLM | `/api/llm` | Provider status, test |
| Insights | `/api/insights` | Direct insight queries |
| Themes | `/api/themes` | Direct theme queries |

## Architecture

```
Browser (Alpine.js + Tailwind + Chart.js)
  |
FastAPI Backend
  |-- SQLite (posts, comments, insights)
  |-- ChromaDB (vector embeddings)
  |-- LLM Providers
        |-- Ollama (local, default)
        |-- Claude API
        |-- OpenAI API
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (async), SQLite
- **Frontend**: Alpine.js, Tailwind CSS, Chart.js (no build step)
- **LLM**: Ollama (default), Claude, OpenAI
- **Vector Search**: ChromaDB with sentence-transformers
- **Reddit Data**: HTTP requests to old.reddit.com (no API key needed)
- **Testing**: pytest, pytest-asyncio
- **CI**: GitHub Actions

## Development

```bash
# Run tests
cd backend
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=term-missing

# Run dev server with hot reload
uvicorn app.main:app --reload --port 8000
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Roadmap

- [x] Core collection and LLM analysis pipeline
- [x] Semantic search with ChromaDB embeddings
- [x] Export (CSV, JSON, Markdown, full research reports)
- [x] Analytics dashboard with Chart.js visualizations
- [x] Audience grouping and filtering with subreddit suggestions
- [x] 117-subreddit catalog across 20 categories
- [x] Security hardening, background tasks, testing, Docker
- [ ] Scheduled collection (APScheduler)
- [ ] Performance improvements (migrations, indexes, rate limiting)

## License

[MIT License](LICENSE)

## Acknowledgments

- Inspired by [GummySearch](https://gummysearch.com) and [PainOnSocial](https://painonsocial.com)
- Built with [Ollama](https://ollama.ai), [FastAPI](https://fastapi.tiangolo.com), [ChromaDB](https://www.trychroma.com)

---

If RedditWatch is useful to you, consider giving it a star — it helps others discover the project.
