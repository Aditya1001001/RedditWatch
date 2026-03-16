"""Aggregated theme model for clustering similar pain points."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.insight import Insight


class Theme(Base):
    """Aggregated theme grouping similar pain points."""

    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Theme info
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True)

    # Scoring
    frequency: Mapped[int] = mapped_column(Integer, default=1)  # Number of related insights
    avg_intensity: Mapped[Optional[float]] = mapped_column(Float)  # Average intensity score
    combined_score: Mapped[Optional[int]] = mapped_column(
        Integer, index=True
    )  # 0-100: weighted score

    # Trend tracking
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime)
    trend: Mapped[Optional[str]] = mapped_column(String(20))  # rising, stable, declining

    # AI-generated solutions (v1.1)
    solutions: Mapped[Optional[str]] = mapped_column(Text)  # JSON array

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    insights: Mapped[list["Insight"]] = relationship(
        "Insight", secondary="insight_themes", back_populates="themes"
    )

    def recalculate_scores(self) -> None:
        """Recalculate frequency, average intensity, and combined score."""
        if not self.insights:
            self.frequency = 0
            self.avg_intensity = None
            self.combined_score = None
            return

        self.frequency = len(self.insights)

        # Calculate average intensity from insights that have scores
        intensities = [i.intensity_score for i in self.insights if i.intensity_score is not None]
        if intensities:
            self.avg_intensity = sum(intensities) / len(intensities)

            # Combined score: weighted average of normalized frequency and intensity
            # Frequency is normalized assuming max ~50 mentions is "very high"
            freq_normalized = min(self.frequency / 50 * 100, 100)
            self.combined_score = int(freq_normalized * 0.4 + self.avg_intensity * 0.6)
        else:
            self.avg_intensity = None
            self.combined_score = None

    def __repr__(self) -> str:
        return f"<Theme {self.id}: {self.title[:40]}... (score={self.combined_score})>"


class InsightTheme(Base):
    """Association table linking insights to themes."""

    __tablename__ = "insight_themes"
    __table_args__ = (
        Index("ix_insight_themes_theme_id", "theme_id"),
    )

    insight_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("insights.id", ondelete="CASCADE"), primary_key=True
    )
    theme_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True
    )
