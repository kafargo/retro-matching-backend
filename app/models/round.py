"""Round model."""
import enum
from sqlalchemy import String, Integer, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class RoundPhase(str, enum.Enum):
    """Phases within a single round."""

    SUBMITTING = "submitting"
    VOTING = "voting"
    COMPLETE = "complete"


class Round(db.Model):
    """A single round within a game."""

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    adjective: Mapped[str] = mapped_column(String(100), nullable=False)
    phase: Mapped[RoundPhase] = mapped_column(
        Enum(RoundPhase, values_callable=lambda e: [v.value for v in e]),
        nullable=False,
        default=RoundPhase.SUBMITTING,
    )

    # Relationships
    game: Mapped["Game"] = relationship(  # type: ignore[name-defined]
        "Game", foreign_keys=[game_id], back_populates="rounds"
    )
    submissions: Mapped[list["Submission"]] = relationship(  # type: ignore[name-defined]
        "Submission", back_populates="round", lazy="select"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="round", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Round number={self.round_number} phase={self.phase}>"
