# RedditWatch

A self-hosted Reddit market research tool for discovering pain points, product opportunities, and market signals. Built as a privacy-first alternative to GummySearch and PainOnSocial.

## Features

- **No Reddit API Keys Required** - Uses public endpoints (old.reddit.com JSON)
- **Local-First** - All data stays on your machine, works offline
- **LLM-Powered Analysis** - Extracts pain points, opportunities, and product mentions
- **Flexible LLM Providers** - Ollama (default, free), Claude, or OpenAI
- **Semantic Search** - Find similar insights using ChromaDB embeddings
- **Web UI** - Browse, filter, and explore insights

## Screenshots

*Coming soon*

## Quick Start

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) with `llama3.1:8b` model (or Claude/OpenAI API key)

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/RedditWatch.git
cd RedditWatch

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Start Ollama (if using local LLM)
ollama serve &
ollama pull llama3.1:8b
```

### Running

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## Usage

### 1. Add Subreddits

Go to the **Subreddits** tab and either:
- Type a subreddit name (e.g., "SaaS") and click Add
- Browse the curated catalog of 53+ startup-relevant subreddits

### 2. Collect Posts

Click **Collect All Posts** on the Dashboard or collect from individual subreddits.

### 3. Analyze with LLM

Go to the **Insights** tab and click **Analyze Posts**. The LLM will extract:
- **Pain Points** - User frustrations with intensity scores (0-100)
- **Solution Requests** - "I wish there was a tool that..."
- **Product Mentions** - Tools/services mentioned with sentiment
- **Opportunities** - Market gaps and unmet needs

### 4. Explore Insights

- **Themes View** - Pain points grouped by theme (e.g., "onboarding_friction")
- **Semantic Search** - Find insights by meaning, not just keywords
- **Filter by Type** - Focus on pain points, opportunities, etc.
- **Click through to Reddit** - Verify insights at the source

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Optional: For Claude API
ANTHROPIC_API_KEY=your_key_here

# Optional: For OpenAI API
OPENAI_API_KEY=your_key_here
```

Edit `backend/config.yaml` to customize:

```yaml
llm:
  provider: ollama  # or "claude" or "openai"
  ollama:
    model: llama3.1:8b
    base_url: http://localhost:11434

collection:
  posts_per_subreddit: 25
  include_comments: true
  max_comments_per_post: 30
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser                           │
│               (Alpine.js + Tailwind CSS)                 │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │ Posts   │ │ Analyze │ │ Search  │ │  LLM    │       │
│  │  API    │ │   API   │ │   API   │ │  API    │       │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │
└─────────────────────────────────────────────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ SQLite  │  │Analyzer │  │ChromaDB │  │  LLM    │
   │   DB    │  │ Service │  │ Vectors │  │Provider │
   └─────────┘  └─────────┘  └─────────┘  └─────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              ▼                ▼                ▼
                         ┌────────┐      ┌────────┐      ┌────────┐
                         │ Ollama │      │ Claude │      │ OpenAI │
                         │ (local)│      │  API   │      │  API   │
                         └────────┘      └────────┘      └────────┘
```

## API Endpoints

### Collection
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/collect` | POST | Collect from all subreddits |
| `/api/subreddits` | GET/POST | List/add subreddits |
| `/api/subreddits/catalog` | GET | Browse curated list |

### Analysis
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | Run LLM analysis |
| `/api/analyze/themes` | GET | Get aggregated themes |
| `/api/analyze/insights` | GET | Get individual insights |

### Search
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search?q=...` | GET | Semantic search |
| `/api/search/similar/{id}` | GET | Find similar insights |

Full API docs at http://localhost:8000/docs

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite
- **Frontend**: Alpine.js, Tailwind CSS (no build step)
- **LLM**: Ollama (default), Claude, OpenAI
- **Vector Search**: ChromaDB with sentence-transformers
- **Reddit Data**: HTTP requests to old.reddit.com (no API key needed)

## Why This Exists

- GummySearch shut down (Nov 2025)
- Paid alternatives cost $20-200/month
- Privacy: Your research data should stay on your machine
- Flexibility: Use any LLM, customize analysis prompts

## Roadmap

- [x] Phase 1-5: Core functionality (collection, analysis, search)
- [ ] Phase 6: Export (CSV, JSON, Markdown)
- [ ] Phase 6.5: Data enrichment (nested comments, engagement tracking)
- [ ] Phase 7: Performance (background jobs, batch processing)
- [ ] Phase 8: UI/UX + Graphs (trend charts, theme networks)

See [DEVLOG.md](DEVLOG.md) for detailed development notes.

## Contributing

Contributions welcome! Please read the DEVLOG.md to understand the architecture.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Inspired by [GummySearch](https://gummysearch.com) and [PainOnSocial](https://painonsocial.com)
- Built with [Ollama](https://ollama.ai), [FastAPI](https://fastapi.tiangolo.com), [ChromaDB](https://www.trychroma.com)
