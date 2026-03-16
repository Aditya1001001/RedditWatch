"""LLM-generated insight model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.post import Post
    from app.models.theme import Theme


class Insight(Base):
    """LLM-generated insight from Reddit content."""

    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source references
    post_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )

    # Classification
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # pain_point, solution_request, product_mention, opportunity
    theme_key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, default="unknown"
    )  # normalized key for grouping: pricing_confusion, onboarding_friction, etc.
    category: Mapped[Optional[str]] = mapped_column(
        String(50), index=True
    )  # pricing, onboarding, integration, etc.

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Evidence
    quote: Mapped[Optional[str]] = mapped_column(Text)
    quote_author: Mapped[Optional[str]] = mapped_column(String(100))
    quote_score: Mapped[Optional[int]] = mapped_column(Integer)
    permalink: Mapped[Optional[str]] = mapped_column(Text)

    # Scoring (PainOnSocial-style)
    intensity_score: Mapped[Optional[int]] = mapped_column(
        Integer, index=True
    )  # 0-100: How severe
    confidence_score: Mapped[Optional[int]] = mapped_column(Integer)  # 0-100: LLM confidence

    # For product mentions
    product_name: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    product_category: Mapped[Optional[str]] = mapped_column(String(100))
    sentiment: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # positive, negative, mixed, neutral

    # Metadata
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50))
    llm_model: Mapped[Optional[str]] = mapped_column(String(100))
    raw_response: Mapped[Optional[str]] = mapped_column(Text)  # Full LLM output for debugging

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="insights")
    themes: Mapped[list["Theme"]] = relationship(
        "Theme", secondary="insight_themes", back_populates="insights"
    )

    @property
    def reddit_url(self) -> Optional[str]:
        """Direct link to the source on Reddit."""
        return f"https://reddit.com{self.permalink}" if self.permalink else None

    def __repr__(self) -> str:
        return f"<Insight {self.id} [{self.type}]: {self.title[:40]}...>"
