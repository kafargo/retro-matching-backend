"""Card model."""
import enum
from sqlalchemy import String, Boolean, Integer, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class CardType(str, enum.Enum):
    """Retrospective card categories."""

    START = "start"
    STOP = "stop"
    CONTINUE = "continue"


class Card(db.Model):
    """A single retrospective card created by a player."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    # holder_id is NULL once the card has been played in a round
    holder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=True, index=True
    )
    card_type: Mapped[CardType] = mapped_column(
        Enum(CardType, values_callable=lambda e: [v.value for v in e]),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    # True once submitted in any round so it cannot be played again
    is_played: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    creator: Mapped["Player"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[creator_id], back_populates="created_cards"
    )
    holder: Mapped["Player | None"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[holder_id], back_populates="held_cards"
    )
    submissions: Mapped[list["Submission"]] = relationship(  # type: ignore[name-defined]
        "Submission", back_populates="card", lazy="select"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="card", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Card type={self.card_type} played={self.is_played}>"
