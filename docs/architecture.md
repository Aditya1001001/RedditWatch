# RedditWatch Architecture

## System Overview

```text
Browser
  Alpine.js + Tailwind + Chart.js
  audiences, discovery, insights, search, Q&A, export
    |
FastAPI backend
  posts, subreddits, audiences, collection, analysis, search, export APIs
    |
    |-- SQLite
    |     posts, comments, audiences, insights, themes, subscriber snapshots
    |
    |-- Reddit collection
    |     public Reddit JSON, RSS fallback, Arctic Shift fallback
    |
    |-- LLM analysis
    |     Ollama by default, optional Claude/OpenAI-compatible providers
    |
    |-- ChromaDB
          semantic insight index for search and retrieval-augmented Q&A
```

## Data Flow

1. A user creates and follows an audience made of subreddits.
2. The collector fetches posts and selected comments from followed audiences.
3. Posts are stored in SQLite and scored for research signal.
4. Deleted, thin, or low-response self-promotional posts can be marked `skipped` before LLM analysis.
5. The analyzer sends high-signal post context to the configured LLM provider.
6. Extracted insights are stored with type, theme, quote, author, source link, and model metadata.
7. Insights are indexed in ChromaDB for semantic search.
8. The UI displays themes, source-backed insight cards, Q&A, and export options.

## Core Models

### Post

- Reddit post metadata: subreddit, title, body, author, score, comments, permalink.
- Analysis state: `analysis_status`, `analysis_error`, `analysis_skip_reason`.
- Research signal: `signal_score`.

### Comment

- Reddit comment metadata, parent relationship, author, score, body, and depth.
- Used as source evidence for insight extraction.

### Insight

- LLM-extracted finding with type, theme, title, description, quote, quote author, product name, sentiment, and source permalink.
- Used for themes, semantic search, Q&A, and exports.

### Audience

- Named research segment made of subreddits.
- `active` controls whether the audience is followed and included in collection.

## Key Subsystems

### Collection

- `backend/app/collectors/reddit.py`
- `backend/app/collectors/arctic_shift.py`
- `backend/app/services/collector.py`

Collection is sequential by default to keep Reddit rate limits predictable. It collects from followed audiences only, uses public Reddit endpoints first, and falls back when Reddit blocks or returns empty responses.

### Analysis

- `backend/app/services/analyzer.py`
- `backend/app/llm/`

Analysis is provider-agnostic. The app defaults to Ollama for local use and can use Claude or OpenAI-compatible APIs. Before calling the LLM, RedditWatch scores posts and skips obvious low-signal candidates.

### Search And Q&A

- `backend/app/services/search.py`
- `backend/app/api/search.py`
- `backend/app/api/audiences.py`

ChromaDB stores insight embeddings. Search and audience Q&A are scoped by audience subreddits so answers stay tied to the selected research segment.

### Runtime Storage

- `data/redditwatch.db` stores app data.
- `data/chroma/` stores the vector index.
- `scripts/reset-runtime-data.sh` archives runtime state and recreates an empty DB for demos.

## Catalog Data

- `backend/app/data/subreddits.yaml`: 283 curated subreddits across 50 categories.
- `backend/app/data/subreddits_directory.json`: 6,089 subreddits with at least 100k subscribers.
- See [subreddit-data-inventory.md](subreddit-data-inventory.md) for details.

## Security And Privacy

RedditWatch is designed as a local/self-hosted app. It does not include authentication and should not be exposed directly to the public internet without access control in front of it.
