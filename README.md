# RedditWatch

[![Tests](https://github.com/Aditya1001001/RedditWatch/actions/workflows/test.yml/badge.svg)](https://github.com/Aditya1001001/RedditWatch/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A self-hosted Reddit market research tool for discovering pain points, product opportunities, and market signals. Built as a privacy-first alternative to GummySearch and PainOnSocial.

## Features

- **No Reddit API Keys Required** - Uses public endpoints (old.reddit.com JSON)
- **Local-First** - All data stays on your machine, works offline
- **LLM-Powered Analysis** - Extracts pain points, opportunities, and product mentions
- **Flexible LLM Providers** - Ollama (default, free), Claude, or OpenAI
- **Semantic Search** - Find similar insights using ChromaDB embeddings
- **Export & Reports** - CSV, JSON, Markdown exports with full research reports
- **Analytics Dashboard** - Charts and visualizations with Chart.js
- **Background Processing** - Collection and analysis run without blocking the UI
- **Web UI** - 6-tab SPA with Alpine.js + Tailwind CSS (no build step)

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

## Usage

### 1. Add Subreddits

Go to the **Subreddits** tab and either:
- Type a subreddit name (e.g., "SaaS") and click Add
- Browse the curated catalog of 53+ startup-relevant subreddits

### 2. Collect Posts

Click **Collect All Posts** on the Dashboard. Collection runs in the background - you can continue using the app.

### 3. Analyze with LLM

Go to the **Insights** tab and click **Analyze Posts**. The LLM extracts:
- **Pain Points** - User frustrations with intensity scores (0-100)
- **Solution Requests** - "I wish there was a tool that..."
- **Product Mentions** - Tools/services mentioned with sentiment
- **Opportunities** - Market gaps and unmet needs

### 4. Explore & Export

- **Themes View** - Pain points grouped by theme (e.g., "onboarding_friction")
- **Semantic Search** - Find insights by meaning, not just keywords
- **Analytics** - Charts showing insight distribution, theme intensity, collection timeline
- **Export** - CSV, JSON, or Markdown. Generate full research reports.

## Configuration

All settings are optional. RedditWatch works out of the box with Ollama.

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

## API Endpoints

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

- [x] Phase 1-5: Core functionality (collection, analysis, search)
- [x] Phase 6: Export (CSV, JSON, Markdown, reports)
- [x] Phase 6.5: Data enrichment (nested comments, engagement tracking)
- [x] Phase 8: Analytics & Visualization (Chart.js dashboards)
- [x] Phase 9: Security hardening, background tasks, testing, Docker
- [ ] Phase 10: Scheduled collection (APScheduler)
- [ ] Phase 11: Performance (migrations, indexes, rate limiting)
- [ ] Phase 12: SaaS foundation (auth, multi-tenancy)

See [DEVLOG.md](DEVLOG.md) for detailed development notes.

## Why This Exists

- GummySearch shut down (Nov 2025)
- Paid alternatives cost $20-200/month
- Privacy: Your research data should stay on your machine
- Flexibility: Use any LLM, customize analysis prompts

## License

[MIT License](LICENSE)

## Acknowledgments

- Inspired by [GummySearch](https://gummysearch.com) and [PainOnSocial](https://painonsocial.com)
- Built with [Ollama](https://ollama.ai), [FastAPI](https://fastapi.tiangolo.com), [ChromaDB](https://www.trychroma.com)
