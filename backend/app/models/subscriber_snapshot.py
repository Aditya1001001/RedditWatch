"""Subscriber count snapshots for tracking subreddit growth."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubscriberSnapshot(Base):
    """A point-in-time record of a subreddit's subscriber count."""

    __tablename__ = "subscriber_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subreddit_name: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("monitored_subreddits.name", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    subscriber_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<SubscriberSnapshot r/{self.subreddit_name}: {self.subscriber_count}>"
