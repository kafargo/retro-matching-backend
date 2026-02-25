"""Vote model — used every round for all-player voting."""
from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class Vote(db.Model):
    """A vote cast by a player during the voting phase of any round."""

    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("round_id", "voter_id", name="uq_round_voter_vote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=False, index=True)
    voter_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("cards.id"), nullable=False)
    voted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    round: Mapped["Round"] = relationship(  # type: ignore[name-defined]
        "Round", back_populates="votes"
    )
    voter: Mapped["Player"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[voter_id], back_populates="votes"
    )
    card: Mapped["Card"] = relationship(  # type: ignore[name-defined]
        "Card", back_populates="votes"
    )

    def __repr__(self) -> str:
        return f"<Vote round={self.round_id} voter={self.voter_id} card={self.card_id}>"
