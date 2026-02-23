"""Round model."""
import enum
from sqlalchemy import String, Boolean, Integer, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class RoundPhase(str, enum.Enum):
    """Phases within a single round."""

    SUBMITTING = "submitting"
    REVEALED = "revealed"
    COMPLETE = "complete"


class Round(db.Model):
    """A single round within a game."""

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # judge_id is NULL for the final round (no judge; everyone votes)
    judge_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("players.id"), nullable=True)
    adjective: Mapped[str] = mapped_column(String(100), nullable=False)
    phase: Mapped[RoundPhase] = mapped_column(
        Enum(RoundPhase, values_callable=lambda e: [v.value for v in e]),
        nullable=False,
        default=RoundPhase.SUBMITTING,
    )
    winner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("players.id"), nullable=True)
    winning_card_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cards.id"), nullable=True)
    is_final_round: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    game: Mapped["Game"] = relationship(  # type: ignore[name-defined]
        "Game", foreign_keys=[game_id], back_populates="rounds"
    )
    judge: Mapped["Player | None"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[judge_id], lazy="select"
    )
    winner: Mapped["Player | None"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[winner_id], lazy="select"
    )
    winning_card: Mapped["Card | None"] = relationship(  # type: ignore[name-defined]
        "Card", foreign_keys=[winning_card_id], lazy="select"
    )
    submissions: Mapped[list["Submission"]] = relationship(  # type: ignore[name-defined]
        "Submission", back_populates="round", lazy="select"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="round", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Round number={self.round_number} phase={self.phase} final={self.is_final_round}>"
