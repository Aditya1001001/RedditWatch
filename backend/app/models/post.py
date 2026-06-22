"""Reddit post model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.insight import Insight


class Post(Base):
    """Reddit post."""

    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_analyzed_created", "analyzed", "created_utc"),
        Index("ix_posts_subreddit_analyzed", "subreddit", "analyzed"),
    )

    # Reddit post ID (e.g., "abc123")
    id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Post metadata
    subreddit: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(String(100))

    # Engagement metrics
    score: Mapped[int] = mapped_column(Integer, default=0)
    upvote_ratio: Mapped[Optional[float]] = mapped_column(Float)
    num_comments: Mapped[int] = mapped_column(Integer, default=0)

    # Flair
    link_flair_text: Mapped[Optional[str]] = mapped_column(String(100))

    # URLs
    permalink: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_utc: Mapped[Optional[datetime]] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Analysis status
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    analysis_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, complete, failed, skipped
    analysis_error: Mapped[Optional[str]] = mapped_column(Text)
    analysis_skip_reason: Mapped[Optional[str]] = mapped_column(Text)
    signal_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    analysis_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    category: Mapped[Optional[str]] = mapped_column(
        String(50), index=True
    )  # pain_point, solution_request, etc.

    # Relationships
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        "Insight", back_populates="post", cascade="all, delete-orphan"
    )

    @property
    def reddit_url(self) -> str:
        """Full Reddit URL for this post."""
        if self.permalink:
            return f"https://reddit.com{self.permalink}"
        return f"https://reddit.com/r/{self.subreddit}/comments/{self.id}"

    def __repr__(self) -> str:
        return f"<Post {self.id} r/{self.subreddit}: {self.title[:50]}...>"
