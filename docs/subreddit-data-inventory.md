# Subreddit Data Inventory

This note records where RedditWatch's subreddit source data lives and what should be preserved when resetting local demo/runtime databases.

## Source Files To Preserve

These files are product/catalog assets, not runtime DB state:

| File | Purpose | Current Size/Count |
| --- | --- | --- |
| `backend/app/data/subreddits.yaml` | Hand-curated catalog used for category browsing and high-quality starter choices. | 50 categories, 283 subreddits |
| `backend/app/data/subreddits_directory.json` | Expanded browsable directory exported from the private enrichment pipeline. Every entry currently has at least 100k subscribers. | 6,089 subreddits |
| `scripts/private/communities.json` | Private full enrichment source. Not for public commits. | 225,905 discovered names, with enrichment data for the high-subscriber slice |
| `scripts/private/popular_subreddits.json` | Earlier popular-subreddit source. Superseded by `communities.json`/directory export for most use cases. | 4,392 entries |

Runtime state can be reset without deleting the files above. Runtime state lives in:

| Path | Meaning |
| --- | --- |
| `data/redditwatch.db` | Local SQLite app database: monitored subreddits, audiences, posts, comments, market signals, snapshots. |
| `data/chroma/` | Local ChromaDB semantic-search index. |
| `data/reset-backups/` | Local backup folder for archived DB/index resets. Ignored by git. |

## Expanded Directory Stats

`backend/app/data/subreddits_directory.json` contains 6,089 subreddits, all at `>= 100,000` subscribers.

Subscriber tiers:

| Tier | Count |
| --- | ---: |
| >= 10M subscribers | 74 |
| >= 5M subscribers | 156 |
| >= 1M subscribers | 856 |
| >= 500K subscribers | 1,536 |
| >= 250K subscribers | 2,779 |
| >= 100K subscribers | 6,089 |

Top examples by subscriber count:

| Subreddit | Subscribers |
| --- | ---: |
| r/funny | 67,123,461 |
| r/AskReddit | 57,992,943 |
| r/worldnews | 47,177,387 |
| r/gaming | 47,026,248 |
| r/todayilearned | 41,289,672 |
| r/Music | 38,330,270 |
| r/aww | 37,701,097 |
| r/movies | 37,262,003 |
| r/memes | 35,699,114 |
| r/science | 34,354,313 |

## Recommended Screen-Recording Starter Subset

For a recording from zero to first aha moment, use a small, market-research-friendly subset instead of importing the full 6,089 directory.

Recommended "SaaS Starter" subset:

| Subreddit | Subscribers | Why include it |
| --- | ---: | --- |
| r/SaaS | 627,709 | Direct SaaS founder/operator questions, pricing, churn, feature needs. |
| r/startups | 2,014,249 | Startup problems, validation, MVP questions, market uncertainty. |
| r/Entrepreneur | 5,113,280 | Broad business-building pain signals and buying-intent discussions. |
| r/ProductManagement | 256,162 | Product workflow, prioritization, research, and roadmap pain. |
| r/marketing | 1,920,714 | Go-to-market, channel, attribution, tooling, and campaign issues. |

Good optional additions if the demo needs more breadth:

| Subreddit | Subscribers | Why include it |
| --- | ---: | --- |
| r/smallbusiness | 2,415,627 | Real operational problems from non-technical businesses. |
| r/webdev | 3,207,921 | Developer tooling, agency, freelance, and implementation pain. |
| r/ecommerce | 621,278 | Merchant workflows, platform/tool frustrations, conversion problems. |
| r/shopify | 342,638 | Concrete product/tool requests from store operators. |
| r/sales | 557,506 | CRM, outbound, lead-gen, and revenue workflow pain. |
| r/SEO | 464,602 | Marketing tooling and search/AI disruption pain. |
| r/LocalLLaMA | 656,458 | AI tooling, self-hosting, model selection, and infra pain. |

Recommended demo flow:

1. Start from an empty runtime DB.
2. Click `Create SaaS Starter`.
3. Click `Collect conversations`.
4. Wait for auto-analysis.
5. Open the audience overview and show the first source-backed signal/top theme.
6. Ask: `What should I pay attention to first?`

## Useful Query Commands

Count expanded directory entries:

```bash
jq 'length' backend/app/data/subreddits_directory.json
```

Count 100k+ entries:

```bash
jq '[.[] | select((.subscribers // 0) >= 100000)] | length' backend/app/data/subreddits_directory.json
```

Get subscriber-tier counts:

```bash
jq '[.[] | .subscribers // 0] as $s | {
  gte_10m: ($s | map(select(. >= 10000000)) | length),
  gte_5m: ($s | map(select(. >= 5000000)) | length),
  gte_1m: ($s | map(select(. >= 1000000)) | length),
  gte_500k: ($s | map(select(. >= 500000)) | length),
  gte_250k: ($s | map(select(. >= 250000)) | length),
  gte_100k: ($s | map(select(. >= 100000)) | length)
}' backend/app/data/subreddits_directory.json
```
