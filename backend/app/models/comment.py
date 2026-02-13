"""Reddit comment model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.post import Post


class Comment(Base):
    """Reddit comment."""

    __tablename__ = "comments"

    # Reddit comment ID
    id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Parent references
    post_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # Parent comment ID or post ID

    # Content
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100))

    # Engagement
    score: Mapped[int] = mapped_column(Integer, default=0)

    # Thread depth (0 = top-level reply to post, 1 = reply to comment, etc.)
    depth: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_utc: Mapped[Optional[datetime]] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment {self.id} on {self.post_id}>"
