# RedditWatch - Self-Hosted Reddit Market Research Tool

## Overview

RedditWatch is a privacy-first, self-hosted alternative to GummySearch and PainOnSocial. It monitors Reddit to identify pain points, solution requests, product mentions, and market opportunities - helping you validate startup ideas with real user feedback.

**Why build this?**
- GummySearch shut down (Nov 2025)
- PainOnSocial costs $19-49/month
- You own your data, run offline, use any LLM

## Competitive Analysis

### What GummySearch Did ($29-199/mo)
- Community discovery (130k+ subreddit database)
- Conversation categorization (Pain Points, Solution Requests, Money Talk, Hot Discussions)
- Keyword tracking with alerts
- Sentiment analysis
- Advanced search/filtering

### What PainOnSocial Does ($19-49/mo)
- Pain point extraction with 0-100 scoring (frequency + intensity)
- Evidence collection with Reddit permalinks
- AI-generated solution ideas per pain point
- Audience analysis
- Curated subreddits by profession (800+)
- Export capabilities

### What RedditWatch Will Do (Free, Self-Hosted)
All the above, running locally with your choice of LLM.

---

## Feature Roadmap

### MVP (Phase 1-4)
| Feature | Description | Inspired By |
|---------|-------------|-------------|
| Subreddit monitoring | Fetch posts/comments on schedule | Both |
| Conversation categorization | Pain Points, Solution Requests, Product Mentions, Opportunities | GummySearch |
| Pain point scoring | 0-100 score based on frequency + intensity | PainOnSocial |
| Evidence collection | Quotes with Reddit permalinks | PainOnSocial |
| Product sentiment | Track what tools people love/hate | GummySearch |
| Search & filter | By subreddit, category, date, keyword, score | Both |
| Export | CSV and JSON | Both |
| Curated subreddits | Pre-built list for entrepreneurs | PainOnSocial |

### v1.1 (Phase 5)
| Feature | Description |
|---------|-------------|
| Solution generation | AI product ideas per pain point |
| Keyword alerts | Notifications when terms appear |
| Trend detection | See pain points growing over time |
| Pain point clustering | Group similar complaints across posts |

### v2 (Future)
| Feature | Description |
|---------|-------------|
| Audience personas | AI-generated user profiles |
| Competitive intelligence | Track specific competitor mentions |
| Dashboard analytics | Charts, trends, summaries |
| Subreddit discovery | Find new relevant communities |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            RedditWatch                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────┐     ┌───────────────┐     ┌────────────────────────┐ │
│  │    Reddit     │     │    SQLite     │     │     LLM Providers      │ │
│  │   Collector   │────▶│   Database    │◀────│  ┌──────────────────┐  │ │
│  │    (PRAW)     │     │               │     │  │ Ollama (default) │  │ │
│  └───────────────┘     └───────┬───────┘     │  │ Claude API       │  │ │
│                                │             │  │ OpenAI API       │  │ │
│  ┌───────────────┐             │             │  └──────────────────┘  │ │
│  │   Scheduler   │             │             └────────────────────────┘ │
│  │ (APScheduler) │             │                                        │
│  └───────────────┘             ▼                                        │
│                         ┌───────────────┐                               │
│                         │    FastAPI    │                               │
│                         │    Backend    │                               │
│                         └───────┬───────┘                               │
│                                 │                                        │
│                                 ▼                                        │
│                         ┌───────────────┐                               │
│                         │    Web UI     │                               │
│                         │  (Alpine.js)  │                               │
│                         └───────────────┘                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Backend | Python 3.11+ / FastAPI | Modern async, great DX |
| Database | SQLite + FTS5 | Zero config, full-text search built-in |
| ORM | SQLAlchemy 2.0 | Mature, async support |
| Reddit API | PRAW | Official wrapper, handles rate limits |
| LLM Integration | httpx | Async HTTP for all providers |
| Frontend | Alpine.js + Tailwind CSS | No build step, lightweight |
| Scheduler | APScheduler | In-process, no Redis needed |
| Containerization | Docker Compose | Easy deployment |

---

## Curated Subreddit Database

### Startup & Entrepreneurship
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/startups | 1.2M | Startup discussion, advice | Early-stage ideas, founder problems |
| r/Entrepreneur | 3.5M | Business and entrepreneurship | Business models, growth tactics |
| r/SaaS | 95K | SaaS-specific discussions | SaaS pain points, pricing, churn |
| r/indiehackers | 45K | Solo founders, bootstrapping | Bootstrapped product ideas |
| r/smallbusiness | 1.8M | Small business owners | SMB problems, local business |
| r/EntrepreneurRideAlong | 180K | Building businesses together | Real-time founder journeys |

### Tech & Development
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/webdev | 2.1M | Web development | Developer tools, frameworks |
| r/programming | 6.5M | General programming | Dev workflow pain points |
| r/devops | 320K | DevOps practices | Infrastructure, CI/CD tools |
| r/selfhosted | 350K | Self-hosting software | Privacy tools, open source |
| r/sysadmin | 850K | System administration | IT infrastructure problems |
| r/node | 220K | Node.js development | JavaScript ecosystem |
| r/reactjs | 380K | React development | Frontend tools |
| r/Python | 1.3M | Python development | Python tools, libraries |

### Product & Design
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/ProductManagement | 95K | Product management | PM tools, roadmap problems |
| r/UXDesign | 180K | UX design | Design tool pain points |
| r/userexperience | 220K | User experience | UX research insights |
| r/web_design | 680K | Web design | Design workflow issues |

### Marketing & Growth
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/marketing | 520K | General marketing | Marketing tool gaps |
| r/digital_marketing | 180K | Digital marketing | Ads, analytics problems |
| r/SEO | 280K | Search optimization | SEO tool opportunities |
| r/content_marketing | 85K | Content marketing | Content tool needs |
| r/socialmedia | 420K | Social media marketing | Social tool pain points |
| r/PPC | 65K | Pay-per-click advertising | Ad platform frustrations |
| r/emailmarketing | 45K | Email marketing | Email tool problems |
| r/Affiliatemarketing | 180K | Affiliate marketing | Affiliate tool needs |

### Remote Work & Productivity
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/remotework | 85K | Remote work discussion | Remote tool gaps |
| r/digitalnomad | 2.8M | Digital nomads | Location-independent tools |
| r/productivity | 1.5M | Productivity tips | Productivity app ideas |
| r/WorkOnline | 580K | Online work | Freelance tool needs |
| r/freelance | 280K | Freelancing | Freelancer pain points |

### Finance & Business Tools
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/accounting | 380K | Accounting professionals | Accounting software gaps |
| r/Bookkeeping | 65K | Bookkeeping | Financial tool needs |
| r/personalfinance | 19M | Personal finance | Fintech opportunities |
| r/FATFire | 520K | High-income earners | Premium tool market |
| r/financialindependence | 2.1M | FIRE movement | Investment tool needs |

### E-commerce & Retail
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/ecommerce | 180K | E-commerce business | E-comm tool pain points |
| r/shopify | 220K | Shopify merchants | Shopify app opportunities |
| r/FulfillmentByAmazon | 120K | Amazon FBA sellers | Amazon seller tools |
| r/dropship | 180K | Dropshipping | Dropship tool needs |
| r/Etsy | 280K | Etsy sellers | Etsy seller problems |

### AI & Automation
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/artificial | 950K | AI discussion | AI tool opportunities |
| r/MachineLearning | 2.8M | ML practitioners | ML tooling gaps |
| r/ChatGPT | 5.2M | ChatGPT users | AI app ideas |
| r/LocalLLaMA | 180K | Local LLM enthusiasts | Local AI tool needs |
| r/automation | 85K | Automation enthusiasts | Automation tool gaps |

### Industry Verticals
| Subreddit | Subscribers | Description | Best For |
|-----------|-------------|-------------|----------|
| r/realtors | 85K | Real estate agents | Real estate tech |
| r/LawFirm | 35K | Law firm management | Legal tech opportunities |
| r/dentistry | 45K | Dental professionals | Dental practice software |
| r/pharmacy | 85K | Pharmacists | Healthcare tech |
| r/restaurateur | 25K | Restaurant owners | Restaurant tech |
| r/Construction | 180K | Construction industry | Construction software |
| r/HVAC | 120K | HVAC professionals | Trade business software |

### Recommended Starter Set
For validating B2B SaaS ideas, start with these 10:
```yaml
subreddits:
  - r/SaaS           # Direct SaaS discussions
  - r/startups       # Founder pain points
  - r/Entrepreneur   # Business problems
  - r/indiehackers   # Bootstrapper needs
  - r/smallbusiness  # SMB problems
  - r/webdev         # Dev tool opportunities
  - r/productivity   # Workflow gaps
  - r/marketing      # Marketing tool needs
  - r/selfhosted     # Privacy-conscious users
  - r/RemoteWork     # Remote tool gaps
```

---

## Project Structure

```
RedditWatch/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entry
│   │   ├── config.py               # Configuration management
│   │   ├── database.py             # SQLite/SQLAlchemy setup
│   │   │
│   │   ├── models/                 # Database models
│   │   │   ├── __init__.py
│   │   │   ├── post.py             # Reddit posts
│   │   │   ├── comment.py          # Reddit comments
│   │   │   ├── insight.py          # LLM-generated insights
│   │   │   ├── subreddit.py        # Monitored subreddits
│   │   │   └── theme.py            # Aggregated pain point themes
│   │   │
│   │   ├── llm/                    # LLM provider system
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Abstract base provider
│   │   │   ├── ollama.py           # Ollama integration
│   │   │   ├── claude.py           # Anthropic Claude API
│   │   │   ├── openai.py           # OpenAI API
│   │   │   └── factory.py          # Provider factory
│   │   │
│   │   ├── collectors/             # Data collection
│   │   │   ├── __init__.py
│   │   │   └── reddit.py           # Reddit collector
│   │   │
│   │   ├── analyzers/              # Analysis pipelines
│   │   │   ├── __init__.py
│   │   │   ├── categorizer.py      # Conversation categorization
│   │   │   ├── pain_points.py      # Pain point extraction + scoring
│   │   │   ├── products.py         # Product mention analysis
│   │   │   ├── opportunities.py    # Market opportunity detection
│   │   │   └── solutions.py        # Solution generation (v1.1)
│   │   │
│   │   ├── api/                    # API routes
│   │   │   ├── __init__.py
│   │   │   ├── posts.py
│   │   │   ├── insights.py
│   │   │   ├── themes.py           # Aggregated themes endpoint
│   │   │   ├── subreddits.py
│   │   │   ├── analysis.py
│   │   │   └── export.py
│   │   │
│   │   └── services/               # Business logic
│   │       ├── __init__.py
│   │       ├── collector.py
│   │       ├── analyzer.py
│   │       └── aggregator.py       # Pain point clustering
│   │
│   ├── data/
│   │   └── subreddits.yaml         # Curated subreddit database
│   │
│   ├── config.yaml
│   ├── requirements.txt
│   └── alembic/
│
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js
│       └── api.js
│
├── data/                           # SQLite DB, exports (gitignored)
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
└── project-context.md
```

---

## Database Schema

### Posts Table
```sql
CREATE TABLE posts (
    id TEXT PRIMARY KEY,              -- Reddit post ID
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    author TEXT,
    score INTEGER,
    upvote_ratio REAL,
    num_comments INTEGER,
    permalink TEXT,                   -- Reddit permalink for linking back
    url TEXT,
    created_utc TIMESTAMP,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analyzed BOOLEAN DEFAULT FALSE,
    category TEXT                     -- pain_point, solution_request, product_mention, discussion, other
);

-- Full-text search index
CREATE VIRTUAL TABLE posts_fts USING fts5(title, body, content=posts, content_rowid=rowid);
```

### Comments Table
```sql
CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    post_id TEXT REFERENCES posts(id) ON DELETE CASCADE,
    parent_id TEXT,
    body TEXT NOT NULL,
    author TEXT,
    score INTEGER,
    created_utc TIMESTAMP,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Insights Table
```sql
CREATE TABLE insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT REFERENCES posts(id) ON DELETE CASCADE,
    comment_id TEXT REFERENCES comments(id) ON DELETE CASCADE,  -- Can be from comment

    -- Classification
    type TEXT NOT NULL,               -- pain_point, solution_request, product_mention, opportunity
    category TEXT,                    -- Sub-category (e.g., "pricing", "onboarding", "integration")

    -- Content
    title TEXT NOT NULL,              -- Short title (5-10 words)
    description TEXT,                 -- Detailed description

    -- Evidence
    quote TEXT,                       -- Direct quote from Reddit
    quote_author TEXT,
    quote_score INTEGER,              -- Upvotes on the quote
    permalink TEXT,                   -- Direct link to source

    -- Scoring (PainOnSocial-style)
    intensity_score INTEGER,          -- 0-100: How severe is this pain?
    confidence_score INTEGER,         -- 0-100: How confident is the LLM?

    -- For product mentions
    product_name TEXT,
    product_category TEXT,
    sentiment TEXT,                   -- positive, negative, mixed, neutral

    -- Metadata
    llm_provider TEXT,
    llm_model TEXT,
    raw_response TEXT,                -- Full LLM output for debugging
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_insights_type ON insights(type);
CREATE INDEX idx_insights_intensity ON insights(intensity_score DESC);
```

### Themes Table (Aggregated Pain Points)
```sql
CREATE TABLE themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Theme info
    title TEXT NOT NULL,              -- Aggregated theme title
    description TEXT,
    category TEXT,

    -- Scoring
    frequency INTEGER DEFAULT 1,      -- How many times this theme appears
    avg_intensity REAL,               -- Average intensity across instances
    combined_score INTEGER,           -- 0-100: frequency * intensity weighted

    -- Trend
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    trend TEXT,                       -- rising, stable, declining

    -- AI-generated solutions (v1.1)
    solutions TEXT,                   -- JSON array of solution ideas

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Link insights to themes
CREATE TABLE insight_themes (
    insight_id INTEGER REFERENCES insights(id) ON DELETE CASCADE,
    theme_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,
    PRIMARY KEY (insight_id, theme_id)
);
```

### Subreddits Table
```sql
CREATE TABLE monitored_subreddits (
    name TEXT PRIMARY KEY,
    display_name TEXT,
    description TEXT,
    subscribers INTEGER,
    category TEXT,                    -- startup, marketing, dev, etc.
    enabled BOOLEAN DEFAULT TRUE,
    last_collected TIMESTAMP,
    post_count INTEGER DEFAULT 0,
    insight_count INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## LLM Provider System

### Base Provider Interface
```python
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None

class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None
    ) -> dict:
        """Generate and parse JSON response."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass
```

### Provider Implementations

**Ollama (Local - Default)**
```python
class OllamaProvider(BaseLLMProvider):
    def __init__(self, config):
        self.base_url = config.llm.ollama.base_url  # http://localhost:11434
        self.model = config.llm.ollama.model        # llama3.1:8b
        self.timeout = config.llm.ollama.timeout    # 120s
```

**Claude API**
```python
class ClaudeProvider(BaseLLMProvider):
    def __init__(self, config):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = config.llm.claude.model        # claude-sonnet-4-20250514
```

**OpenAI API**
```python
class OpenAIProvider(BaseLLMProvider):
    def __init__(self, config):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = config.llm.openai.model        # gpt-4o-mini
```

### Factory with Fallback
```python
class LLMProviderFactory:
    @staticmethod
    async def get_provider(config) -> BaseLLMProvider:
        providers = {
            "ollama": OllamaProvider,
            "claude": ClaudeProvider,
            "openai": OpenAIProvider,
        }

        # Try primary
        primary = providers[config.llm.provider](config)
        if await primary.is_available():
            return primary

        # Try fallbacks
        for name in config.llm.fallback_chain:
            fallback = providers[name](config)
            if await fallback.is_available():
                logger.warning(f"Using fallback: {name}")
                return fallback

        raise LLMProviderError("No LLM providers available")
```

---

## Analysis Prompts

### Conversation Categorizer
```
Categorize this Reddit post into one of these types:

- pain_point: User expressing frustration, problem, or unmet need
- solution_request: User asking for tool/product recommendations
- product_mention: Discussion about specific products/tools
- opportunity: User describing workaround or "I wish..." statement
- discussion: General discussion without clear signal
- other: Doesn't fit other categories

POST:
Subreddit: r/{subreddit}
Title: {title}
Body: {body}

Respond with JSON:
{
  "category": "pain_point|solution_request|product_mention|opportunity|discussion|other",
  "confidence": 0-100,
  "reasoning": "brief explanation"
}
```

### Pain Point Extractor with Scoring
```
Analyze this Reddit discussion for pain points - problems, frustrations, or unmet needs.

For each pain point, extract:
1. title: Short description (5-10 words)
2. description: Detailed explanation
3. category: pricing|onboarding|integration|performance|support|features|workflow|other
4. intensity_score: 0-100 based on:
   - Emotional language (frustration, anger, desperation)
   - Impact described (time wasted, money lost, blocked)
   - Urgency expressed
5. quote: Exact quote that best represents this pain
6. quote_author: Username of the person quoted

POST:
Subreddit: r/{subreddit}
Title: {title}
Body: {body}
Author: {author}

TOP COMMENTS (sorted by score):
{comments}

Respond with JSON array:
[
  {
    "title": "...",
    "description": "...",
    "category": "...",
    "intensity_score": 0-100,
    "quote": "exact quote from post or comment",
    "quote_author": "username"
  }
]

Return empty array [] if no clear pain points found.
```

### Product Mention Analyzer
```
Identify products, tools, services, or companies mentioned in this discussion.

For each product, extract:
1. name: Product/company name
2. category: Type of product (e.g., "CRM", "email marketing", "analytics")
3. sentiment: positive|negative|mixed|neutral
4. feedback: Key points people make about it
5. quote: Supporting quote
6. competitor_of: If mentioned as alternative to another product

POST:
{content}

COMMENTS:
{comments}

Respond with JSON array:
[
  {
    "name": "ProductName",
    "category": "product category",
    "sentiment": "positive|negative|mixed|neutral",
    "feedback": ["point 1", "point 2"],
    "quote": "what someone said",
    "competitor_of": "OtherProduct or null"
  }
]
```

### Opportunity Detector
```
Analyze this discussion for market opportunities and potential product ideas.

Look for:
- Gaps in existing solutions
- Feature requests
- "I wish there was..." statements
- Manual workarounds people describe
- Willingness to pay signals ("I'd pay for...", "worth any price")

For each opportunity, extract:
1. title: Opportunity description (5-10 words)
2. description: What could be built
3. target_audience: Who would use this
4. existing_alternatives: What people currently use (if mentioned)
5. willingness_to_pay: none|implied|explicit
6. quote: Supporting quote
7. intensity_score: 0-100 based on urgency and demand signals

POST:
{content}

Respond with JSON array.
```

### Solution Generator (v1.1)
```
Based on this pain point theme, generate practical product/service ideas.

PAIN POINT THEME:
Title: {title}
Description: {description}
Frequency: Mentioned {frequency} times
Average Intensity: {avg_intensity}/100
Sample Quotes:
{quotes}

Generate 3-5 solution ideas. For each:
1. name: Catchy product name
2. description: What it does (2-3 sentences)
3. type: saas|marketplace|tool|service|content|community
4. complexity: mvp|moderate|complex
5. monetization: How it could make money
6. existing_competitors: Known alternatives (if any)
7. differentiation: What makes this unique

Respond with JSON array.
```

---

## Configuration

### config.yaml
```yaml
# RedditWatch Configuration

# Reddit API (create app at https://www.reddit.com/prefs/apps)
reddit:
  client_id: "${REDDIT_CLIENT_ID}"
  client_secret: "${REDDIT_CLIENT_SECRET}"
  user_agent: "RedditWatch/1.0 (self-hosted market research)"

# LLM Configuration
llm:
  # Primary: ollama (local), claude, or openai
  provider: "ollama"

  # Fallback order if primary unavailable
  fallback_chain:
    - "claude"
    - "openai"

  ollama:
    base_url: "http://localhost:11434"
    model: "llama3.1:8b"
    timeout: 120

  claude:
    model: "claude-sonnet-4-20250514"
    max_tokens: 4096

  openai:
    model: "gpt-4o-mini"
    max_tokens: 4096

# Collection settings
collection:
  interval_minutes: 30
  posts_per_subreddit: 25
  include_comments: true
  max_comments_per_post: 30
  sort_by: "hot"  # hot, new, top, rising

# Analysis settings
analysis:
  auto_analyze: true
  batch_size: 5
  min_score_threshold: 3  # Ignore posts with < 3 upvotes

# Scoring weights (for combined theme score)
scoring:
  frequency_weight: 0.4
  intensity_weight: 0.6

# Server
server:
  host: "0.0.0.0"
  port: 8000
```

### .env.example
```bash
# Reddit API (required)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret

# Cloud LLM keys (optional - only if using cloud providers)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## API Endpoints

### Posts
- `GET /api/posts` - List posts (filters: subreddit, category, analyzed, date_range)
- `GET /api/posts/{id}` - Get post with comments and insights
- `DELETE /api/posts/{id}` - Delete post and cascade

### Insights
- `GET /api/insights` - List insights (filters: type, min_intensity, subreddit)
- `GET /api/insights/stats` - Aggregate stats by type, category
- `GET /api/insights/{id}` - Get single insight with source

### Themes (Aggregated Pain Points)
- `GET /api/themes` - List themes sorted by combined_score
- `GET /api/themes/{id}` - Get theme with all related insights
- `POST /api/themes/{id}/generate-solutions` - Generate solution ideas (v1.1)

### Products
- `GET /api/products` - List mentioned products with sentiment
- `GET /api/products/{name}/mentions` - All mentions of a product

### Subreddits
- `GET /api/subreddits` - List monitored subreddits
- `GET /api/subreddits/catalog` - Browse curated subreddit database
- `POST /api/subreddits` - Add subreddit to monitor
- `DELETE /api/subreddits/{name}` - Stop monitoring

### Analysis
- `POST /api/analyze` - Analyze unanalyzed posts
- `POST /api/analyze/post/{id}` - Re-analyze specific post
- `GET /api/analyze/status` - Job status

### Collection
- `POST /api/collect` - Trigger immediate collection
- `GET /api/collect/status` - Collector status

### Export
- `GET /api/export/insights?format=csv|json` - Export insights
- `GET /api/export/themes?format=csv|json` - Export themes
- `GET /api/export/products?format=csv|json` - Export product mentions

### System
- `GET /api/health` - Health check
- `GET /api/llm/status` - LLM provider status
- `POST /api/llm/test` - Test LLM connection

---

## Implementation Phases

### Phase 1: Foundation
**Goal: Working infrastructure, can talk to LLM**

- [ ] Project setup (pyproject.toml, requirements.txt)
- [ ] Directory structure
- [ ] Config system (YAML + env vars + Pydantic)
- [ ] Database setup (SQLAlchemy + SQLite)
- [ ] LLM provider: Ollama implementation
- [ ] LLM provider: Factory + health check
- [ ] Basic FastAPI app with /health endpoint

**Milestone: `POST /api/llm/test` returns response from Ollama**

### Phase 2: Reddit Collection
**Goal: Fetch and store Reddit data**

- [ ] PRAW integration
- [ ] Reddit collector (posts + comments)
- [ ] Subreddit management endpoints
- [ ] APScheduler for periodic collection
- [ ] Curated subreddit catalog endpoint
- [ ] Post listing endpoint with filters

**Milestone: Can add subreddit, fetch posts, view via API**

### Phase 3: LLM Analysis
**Goal: Extract insights with scoring**

- [ ] Conversation categorizer
- [ ] Pain point extractor with intensity scoring
- [ ] Product mention analyzer
- [ ] Opportunity detector
- [ ] Analysis service (batch processing)
- [ ] Insights endpoints

**Milestone: Posts get analyzed, insights have scores**

### Phase 4: Aggregation & UI
**Goal: Usable web interface**

- [ ] Theme aggregation (cluster similar pain points)
- [ ] Combined scoring (frequency * intensity)
- [ ] Frontend: Dashboard with stats
- [ ] Frontend: Insights browser with filters
- [ ] Frontend: Theme view
- [ ] Frontend: Product mentions view
- [ ] Export functionality (CSV/JSON)

**Milestone: Browse insights in web UI, export data**

### Phase 5: Polish & Deploy
**Goal: Production-ready**

- [ ] Claude API provider
- [ ] OpenAI API provider
- [ ] Fallback logic
- [ ] Docker setup
- [ ] Error handling & logging
- [ ] Documentation

**Milestone: Docker image works, can switch LLM providers**

### Phase 6: v1.1 Features
**Goal: Advanced features**

- [ ] Solution generation per theme
- [ ] Keyword alerts
- [ ] Trend detection (rising/falling pain points)
- [ ] Pain point clustering improvements

---

## Getting Started

```bash
# Setup
cd RedditWatch
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Configure
cp .env.example .env
# Edit .env with Reddit API credentials
cp backend/config.example.yaml backend/config.yaml

# Ensure Ollama is running
ollama serve &
ollama pull llama3.1:8b

# Initialize database
cd backend
python -m app.database init

# Run
uvicorn app.main:app --reload --port 8000

# Open
open http://localhost:8000
```

---

## Success Criteria

1. **Privacy**: All data local, works offline with Ollama
2. **Useful**: Surface actionable pain points, not noise
3. **Flexible**: Easy to switch LLMs, add subreddits
4. **Fast setup**: Under 15 minutes to first insight
5. **Exportable**: Get data out in standard formats
6. **Maintainable**: Clean code, easy to extend

---

## Build Order Recommendation

**Start with Phase 1, specifically:**

1. `backend/app/config.py` - Config loading
2. `backend/app/database.py` - SQLAlchemy setup
3. `backend/app/llm/base.py` - Provider interface
4. `backend/app/llm/ollama.py` - Ollama implementation
5. `backend/app/main.py` - FastAPI app with health + LLM test endpoints

This gives you a working foundation to build everything else on top of.
