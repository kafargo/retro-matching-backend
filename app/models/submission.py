"""Submission model."""
from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class Submission(db.Model):
    """A card played by a player into a round."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("round_id", "player_id", name="uq_round_player_submission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("cards.id"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    round: Mapped["Round"] = relationship(  # type: ignore[name-defined]
        "Round", back_populates="submissions"
    )
    player: Mapped["Player"] = relationship(  # type: ignore[name-defined]
        "Player", back_populates="submissions"
    )
    card: Mapped["Card"] = relationship(  # type: ignore[name-defined]
        "Card", back_populates="submissions"
    )

    def __repr__(self) -> str:
        return f"<Submission round={self.round_id} player={self.player_id}>"
