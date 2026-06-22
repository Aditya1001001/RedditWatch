"""Export API endpoints for insights, themes, and reports."""

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.models import Insight, Post
from app.services.analyzer import get_analyzer

router = APIRouter()

SIGNAL_TYPE_LABELS = {
    "pain_point": "Pain Signal",
    "solution_request": "Demand Signal",
    "opportunity": "Opportunity Signal",
    "product_mention": "Product Mention",
    "advice_request": "Advice Signal",
    "idea": "Idea Signal",
    "money_talk": "Pricing Signal",
}


class ExportFilters(BaseModel):
    """Filters for export."""
    type: Optional[str] = None
    theme_key: Optional[str] = None
    min_intensity: Optional[int] = None
    max_intensity: Optional[int] = None
    subreddit: Optional[str] = None
    ids: Optional[list[int]] = None


def insights_to_csv(insights: list[Insight]) -> str:
    """Convert insights to CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id", "type", "theme_key", "title", "description",
        "quote", "quote_author", "intensity_score",
        "product_name", "sentiment", "subreddit",
        "reddit_url", "created_at"
    ])

    # Rows
    for insight in insights:
        writer.writerow([
            insight.id,
            insight.type,
            insight.theme_key,
            insight.title,
            insight.description or "",
            insight.quote or "",
            insight.quote_author or "",
            insight.intensity_score or "",
            insight.product_name or "",
            insight.sentiment or "",
            insight.post.subreddit if insight.post else "",
            insight.reddit_url or "",
            insight.created_at.isoformat() if insight.created_at else "",
        ])

    return output.getvalue()


def insights_to_json(insights: list[Insight]) -> list[dict]:
    """Convert insights to JSON-serializable format."""
    return [
        {
            "id": insight.id,
            "type": insight.type,
            "theme_key": insight.theme_key,
            "title": insight.title,
            "description": insight.description,
            "quote": insight.quote,
            "quote_author": insight.quote_author,
            "intensity_score": insight.intensity_score,
            "product_name": insight.product_name,
            "sentiment": insight.sentiment,
            "subreddit": insight.post.subreddit if insight.post else None,
            "reddit_url": insight.reddit_url,
            "post_title": insight.post.title if insight.post else None,
            "created_at": insight.created_at.isoformat() if insight.created_at else None,
        }
        for insight in insights
    ]


def insights_to_markdown(insights: list[Insight], include_summary: bool = True) -> str:
    """Convert insight records to a market signal Markdown report."""
    lines = []

    # Header
    lines.append("# RedditWatch Market Signals Export")
    lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"\n*Total signals: {len(insights)}*\n")

    # Summary by type
    if include_summary:
        type_counts = {}
        for insight in insights:
            type_counts[insight.type] = type_counts.get(insight.type, 0) + 1

        lines.append("## Signal Breakdown\n")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {SIGNAL_TYPE_LABELS.get(t, t.replace('_', ' ').title())} | {count} |")
        lines.append("")

    # Group by theme
    themes = {}
    for insight in insights:
        key = insight.theme_key
        if key not in themes:
            themes[key] = []
        themes[key].append(insight)

    # Sort themes by count
    sorted_themes = sorted(themes.items(), key=lambda x: -len(x[1]))

    lines.append("---\n")
    lines.append("## Signals by Theme\n")

    for theme_key, theme_insights in sorted_themes:
        theme_name = theme_key.replace("_", " ").title()
        avg_intensity = sum(i.intensity_score or 0 for i in theme_insights) / len(theme_insights)

        lines.append(f"### {theme_name}")
        lines.append(f"*{len(theme_insights)} signals | Avg signal strength: {avg_intensity:.0f}*\n")

        for insight in theme_insights:
            # Type badge
            type_emoji = {
                "pain_point": "🔴",
                "solution_request": "🟡",
                "opportunity": "🟢",
                "product_mention": "🟣",
                "advice_request": "🔵",
                "idea": "🟠",
                "money_talk": "🩵",
            }.get(insight.type, "⚪")

            lines.append(f"#### {type_emoji} {insight.title}")

            if insight.description:
                lines.append(f"\n{insight.description}\n")

            if insight.quote:
                lines.append(f"> \"{insight.quote}\"")
                if insight.quote_author:
                    lines.append(f"> — {insight.quote_author}")
                lines.append("")

            # Metadata line
            meta = []
            if insight.intensity_score:
                meta.append(f"Signal strength: {insight.intensity_score}/100")
            if insight.product_name:
                meta.append(f"Product: {insight.product_name}")
            if insight.sentiment:
                meta.append(f"Sentiment: {insight.sentiment}")
            if insight.reddit_url:
                meta.append(f"[Source]({insight.reddit_url})")

            if meta:
                lines.append(f"*{' | '.join(meta)}*\n")

        lines.append("---\n")

    return "\n".join(lines)


def generate_quote_card(insight: Insight) -> str:
    """Generate a shareable quote card in Markdown."""
    lines = []

    type_label = SIGNAL_TYPE_LABELS.get(insight.type, insight.type.replace("_", " ").title())

    lines.append("```")
    lines.append("┌─────────────────────────────────────────┐")
    lines.append(f"│ {type_label.upper():<39} │")
    lines.append("├─────────────────────────────────────────┤")

    if insight.quote:
        # Word wrap quote to ~35 chars per line
        quote = insight.quote
        words = quote.split()
        current_line = "│ \""
        for word in words:
            if len(current_line) + len(word) + 1 > 40:
                lines.append(f"{current_line:<42}│")
                current_line = "│  " + word
            else:
                current_line += " " + word if current_line != "│ \"" else word
        current_line += "\""
        lines.append(f"{current_line:<42}│")

        if insight.quote_author:
            lines.append(f"│ — {insight.quote_author:<37} │")

    lines.append("├─────────────────────────────────────────┤")

    if insight.intensity_score:
        intensity_bar = "█" * (insight.intensity_score // 10) + "░" * (10 - insight.intensity_score // 10)
        lines.append(f"│ Strength:  [{intensity_bar}] {insight.intensity_score:>3} │")

    lines.append(f"│ Theme: {insight.theme_key.replace('_', ' '):<32} │")
    lines.append("└─────────────────────────────────────────┘")
    lines.append("```")

    if insight.reddit_url:
        lines.append(f"\n[View on Reddit]({insight.reddit_url})")

    return "\n".join(lines)


async def get_filtered_insights(
    session: AsyncSession,
    type_filter: Optional[str] = None,
    theme_key: Optional[str] = None,
    min_intensity: Optional[int] = None,
    max_intensity: Optional[int] = None,
    subreddit: Optional[str] = None,
    subreddit_names: Optional[list[str]] = None,
    ids: Optional[list[int]] = None,
    limit: int = 500,
) -> list[Insight]:
    """Get insights with filters applied."""
    query = select(Insight).options(joinedload(Insight.post)).join(Post)

    if ids:
        query = query.where(Insight.id.in_(ids))
    if type_filter:
        query = query.where(Insight.type == type_filter)
    if theme_key:
        query = query.where(Insight.theme_key == theme_key)
    if min_intensity is not None:
        query = query.where(Insight.intensity_score >= min_intensity)
    if max_intensity is not None:
        query = query.where(Insight.intensity_score <= max_intensity)
    if subreddit:
        query = query.where(Post.subreddit == subreddit.lower())
    elif subreddit_names is not None:
        query = query.where(Post.subreddit.in_(subreddit_names))

    query = query.order_by(Insight.intensity_score.desc().nullslast())
    query = query.limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/insights")
async def export_insights(
    format: str = Query(default="json", pattern="^(json|csv|markdown|md)$"),
    type: Optional[str] = Query(default=None, alias="type"),
    theme_key: Optional[str] = None,
    min_intensity: Optional[int] = Query(default=None, ge=0, le=100),
    max_intensity: Optional[int] = Query(default=None, ge=0, le=100),
    subreddit: Optional[str] = None,
    audience_id: Optional[int] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
):
    """
    Export market signals in various formats.

    Args:
        format: Output format (json, csv, markdown/md)
        type: Filter by internal insight/signal type
        theme_key: Filter by theme key
        min_intensity: Minimum signal strength score
        max_intensity: Maximum signal strength score
        subreddit: Filter by source subreddit
        limit: Maximum number of signals to export

    Returns:
        Signals in requested format
    """
    # Resolve audience to subreddit filter
    effective_subreddit = subreddit
    if audience_id and not subreddit:
        from app.api.analysis import resolve_audience_subreddits
        sub_names = await resolve_audience_subreddits(session, audience_id)
        if sub_names:
            # get_filtered_insights only supports single subreddit, so we pass the list directly
            insights = await get_filtered_insights(
                session,
                type_filter=type,
                theme_key=theme_key,
                min_intensity=min_intensity,
                max_intensity=max_intensity,
                subreddit_names=sub_names,
                limit=limit,
            )
        else:
            insights = []
    else:
        insights = await get_filtered_insights(
            session,
            type_filter=type,
            theme_key=theme_key,
            min_intensity=min_intensity,
            max_intensity=max_intensity,
            subreddit=effective_subreddit,
            limit=limit,
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if format == "csv":
        content = insights_to_csv(insights)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="signals_{timestamp}.csv"'
            }
        )

    elif format in ("markdown", "md"):
        content = insights_to_markdown(insights)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="signals_{timestamp}.md"'
            }
        )

    else:  # json
        return {
            "exported_at": datetime.now().isoformat(),
            "count": len(insights),
            "filters": {
                "type": type,
                "theme_key": theme_key,
                "min_intensity": min_intensity,
                "max_intensity": max_intensity,
                "subreddit": subreddit,
            },
            "insights": insights_to_json(insights),
        }


@router.post("/insights/selected")
async def export_selected_insights(
    ids: list[int],
    format: str = Query(default="json", pattern="^(json|csv|markdown|md)$"),
    session: AsyncSession = Depends(get_session),
):
    """
    Export specific market signals by ID.

    Args:
        ids: List of internal insight/signal IDs to export
        format: Output format (json, csv, markdown/md)
    """
    insights = await get_filtered_insights(session, ids=ids, limit=len(ids))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if format == "csv":
        content = insights_to_csv(insights)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="signals_selected_{timestamp}.csv"'
            }
        )

    elif format in ("markdown", "md"):
        content = insights_to_markdown(insights)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="signals_selected_{timestamp}.md"'
            }
        )

    else:
        return {
            "exported_at": datetime.now().isoformat(),
            "count": len(insights),
            "insights": insights_to_json(insights),
        }


@router.get("/insights/{insight_id}/quote-card")
async def get_quote_card(
    insight_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a shareable quote card for a market signal.

    Returns Markdown-formatted quote card.
    """
    insight = await session.get(Insight, insight_id)
    if not insight:
        return Response(status_code=404, content="Signal not found")

    card = generate_quote_card(insight)

    return Response(
        content=card,
        media_type="text/markdown",
    )


@router.get("/themes")
async def export_themes(
    format: str = Query(default="json", pattern="^(json|csv|markdown|md)$"),
    session: AsyncSession = Depends(get_session),
):
    """
    Export aggregated themes.

    Args:
        format: Output format (json, csv, markdown/md)
    """
    analyzer = get_analyzer()
    themes = await analyzer.get_theme_summary(session)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "theme_key", "count", "avg_intensity", "combined_score", "types"
        ])
        for theme in themes:
            writer.writerow([
                theme["theme_key"],
                theme["count"],
                theme["avg_intensity"],
                theme["combined_score"],
                ", ".join(theme["types"]),
            ])

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="themes_{timestamp}.csv"'
            }
        )

    elif format in ("markdown", "md"):
        lines = []
        lines.append("# RedditWatch Signal Themes Export")
        lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        lines.append(f"\n*Total themes: {len(themes)}*\n")

        lines.append("| Theme | Count | Avg Signal Strength | Combined Score | Signal Types |")
        lines.append("|-------|-------|---------------|----------------|-------|")

        for theme in themes:
            theme_name = theme["theme_key"].replace("_", " ").title()
            types = ", ".join(SIGNAL_TYPE_LABELS.get(t, t.replace("_", " ")) for t in theme["types"])
            lines.append(
                f"| {theme_name} | {theme['count']} | {theme['avg_intensity']:.1f} | "
                f"{theme['combined_score']:.1f} | {types} |"
            )

        lines.append("\n---\n")
        lines.append("## Top Quotes by Theme\n")

        for theme in themes[:10]:  # Top 10 themes
            if theme["top_quotes"]:
                theme_name = theme["theme_key"].replace("_", " ").title()
                lines.append(f"### {theme_name}\n")
                for quote in theme["top_quotes"][:3]:
                    lines.append(f"> \"{quote['quote']}\"")
                    lines.append(f"> — {quote['author']}\n")

        return Response(
            content="\n".join(lines),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="themes_{timestamp}.md"'
            }
        )

    else:
        return {
            "exported_at": datetime.now().isoformat(),
            "count": len(themes),
            "themes": themes,
        }


@router.get("/report")
async def generate_report(
    audience_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a comprehensive Markdown report with all market signals and themes.

    This is a full export suitable for sharing or archiving.
    """
    analyzer = get_analyzer()

    # Resolve audience filter
    sub_names = None
    if audience_id:
        from app.api.analysis import resolve_audience_subreddits
        sub_names = await resolve_audience_subreddits(session, audience_id)

    # Get all data
    themes = await analyzer.get_theme_summary(session, subreddit_names=sub_names)
    insights = await get_filtered_insights(session, subreddit_names=sub_names, limit=1000)

    # Get stats
    from sqlalchemy import func
    total_posts = await session.execute(select(func.count(Post.id)))
    analyzed_posts = await session.execute(
        select(func.count(Post.id)).where(Post.analyzed == True)
    )

    lines = []

    # Title
    lines.append("# RedditWatch Market Signals Report")
    lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append(f"- **Posts analyzed**: {analyzed_posts.scalar() or 0} of {total_posts.scalar() or 0}")
    lines.append(f"- **Market signals extracted**: {len(insights)}")
    lines.append(f"- **Themes identified**: {len(themes)}")

    # Type breakdown
    type_counts = {}
    for insight in insights:
        type_counts[insight.type] = type_counts.get(insight.type, 0) + 1

    lines.append("\n### Signal Breakdown\n")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        emoji = {"pain_point": "🔴", "solution_request": "🟡", "opportunity": "🟢", "product_mention": "🟣", "advice_request": "🔵", "idea": "🟠", "money_talk": "🩵"}.get(t, "⚪")
        lines.append(f"- {emoji} **{SIGNAL_TYPE_LABELS.get(t, t.replace('_', ' ').title())}**: {count}")

    # Top Themes
    lines.append("\n---\n")
    lines.append("## Top Themes\n")
    lines.append("*Sorted by combined score (frequency x signal strength)*\n")

    for i, theme in enumerate(themes[:15], 1):
        theme_name = theme["theme_key"].replace("_", " ").title()
        lines.append(f"### {i}. {theme_name}")
        lines.append(f"- **Occurrences**: {theme['count']}")
        lines.append(f"- **Average signal strength**: {theme['avg_intensity']:.0f}/100")
        lines.append(f"- **Combined score**: {theme['combined_score']:.1f}")
        lines.append(f"- **Types**: {', '.join(theme['types'])}")

        if theme["top_quotes"]:
            lines.append("\n**Key quotes:**")
            for quote in theme["top_quotes"][:2]:
                lines.append(f"> \"{quote['quote']}\"")
                lines.append(f"> — {quote['author']}\n")
        lines.append("")

    # High-strength pain signals
    high_intensity = [i for i in insights if i.type == "pain_point" and (i.intensity_score or 0) >= 70]
    if high_intensity:
        lines.append("---\n")
        lines.append("## High-Strength Pain Signals (70+)\n")
        lines.append("*These represent the strongest repeated frustrations found in the source conversations.*\n")

        for insight in sorted(high_intensity, key=lambda x: -(x.intensity_score or 0))[:10]:
            lines.append(f"### {insight.title}")
            lines.append(f"*Signal strength: {insight.intensity_score}/100 | Theme: {insight.theme_key.replace('_', ' ')}*\n")
            if insight.description:
                lines.append(f"{insight.description}\n")
            if insight.quote:
                lines.append(f"> \"{insight.quote}\"")
                if insight.quote_author:
                    lines.append(f"> — {insight.quote_author}")
            if insight.reddit_url:
                lines.append(f"\n[View source]({insight.reddit_url})\n")
            lines.append("")

    # Opportunities
    opportunities = [i for i in insights if i.type == "opportunity"]
    if opportunities:
        lines.append("---\n")
        lines.append("## Opportunities Identified\n")

        for insight in opportunities[:10]:
            lines.append(f"### {insight.title}")
            if insight.description:
                lines.append(f"\n{insight.description}\n")
            if insight.quote:
                lines.append(f"> \"{insight.quote}\"")
                if insight.quote_author:
                    lines.append(f"> — {insight.quote_author}")
            if insight.reddit_url:
                lines.append(f"\n[View source]({insight.reddit_url})\n")
            lines.append("")

    # Product Mentions
    products = [i for i in insights if i.type == "product_mention" and i.product_name]
    if products:
        lines.append("---\n")
        lines.append("## Product Mentions\n")

        # Group by product
        by_product = {}
        for p in products:
            name = p.product_name
            if name not in by_product:
                by_product[name] = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "quotes": []}
            sentiment = p.sentiment or "neutral"
            by_product[name][sentiment] = by_product[name].get(sentiment, 0) + 1
            if p.quote:
                by_product[name]["quotes"].append({"quote": p.quote, "author": p.quote_author, "sentiment": sentiment})

        lines.append("| Product | Positive | Negative | Neutral | Mixed |")
        lines.append("|---------|----------|----------|---------|-------|")
        for name, data in sorted(by_product.items(), key=lambda x: -sum(v for k, v in x[1].items() if k != "quotes")):
            lines.append(f"| {name} | {data['positive']} | {data['negative']} | {data['neutral']} | {data['mixed']} |")
        lines.append("")

    # Footer
    lines.append("---\n")
    lines.append("*Report generated by [RedditWatch](https://github.com/Aditya1001001/RedditWatch)*")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="redditwatch_report_{timestamp}.md"'
        }
    )
