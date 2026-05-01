"""Audience model for grouping subreddits."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Many-to-many association table
audience_subreddits = Table(
    "audience_subreddits",
    Base.metadata,
    Column(
        "audience_id",
        Integer,
        ForeignKey("audiences.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "subreddit_name",
        String(100),
        ForeignKey("monitored_subreddits.name", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Audience(Base):
    """A named group of subreddits for filtering insights."""

    __tablename__ = "audiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(String(7))  # hex color e.g. #d4a373
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Many-to-many with MonitoredSubreddit
    subreddits = relationship(
        "MonitoredSubreddit",
        secondary=audience_subreddits,
        backref="audiences",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Audience {self.name} ({len(self.subreddits)} subreddits)>"
