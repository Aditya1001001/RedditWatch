"""Monitored subreddit model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MonitoredSubreddit(Base):
    """A subreddit being monitored for insights."""

    __tablename__ = "monitored_subreddits"

    # Subreddit name (without r/ prefix)
    name: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Display info
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    subscribers: Mapped[Optional[int]] = mapped_column(Integer)

    # Categorization
    category: Mapped[Optional[str]] = mapped_column(
        String(50), index=True
    )  # startup, marketing, dev, etc.

    # Status
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Collection stats
    last_collected: Mapped[Optional[datetime]] = mapped_column(DateTime)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    insight_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    added_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    @property
    def reddit_url(self) -> str:
        """URL to the subreddit."""
        return f"https://reddit.com/r/{self.name}"

    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"<MonitoredSubreddit r/{self.name} ({status})>"
