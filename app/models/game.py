"""Game model."""
import enum
from datetime import datetime
from sqlalchemy import String, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class GamePhase(str, enum.Enum):
    """Game lifecycle phases."""

    LOBBY = "lobby"
    CARD_CREATION = "card_creation"
    PLAYING = "playing"
    FINAL_ROUND = "final_round"
    FINISHED = "finished"


class Game(db.Model):
    """Represents a single game session."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    phase: Mapped[GamePhase] = mapped_column(
        Enum(GamePhase, values_callable=lambda e: [v.value for v in e]),
        nullable=False,
        default=GamePhase.LOBBY,
    )
    creator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("players.id"), nullable=True)
    current_round_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("rounds.id", use_alter=True, name="fk_game_current_round"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    players: Mapped[list["Player"]] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys="Player.game_id", back_populates="game", lazy="select"
    )
    rounds: Mapped[list["Round"]] = relationship(  # type: ignore[name-defined]
        "Round", foreign_keys="Round.game_id", back_populates="game", lazy="select"
    )
    creator: Mapped["Player | None"] = relationship(  # type: ignore[name-defined]
        "Player", foreign_keys=[creator_id], lazy="select"
    )
    current_round: Mapped["Round | None"] = relationship(  # type: ignore[name-defined]
        "Round", foreign_keys=[current_round_id], lazy="select", post_update=True
    )

    def __repr__(self) -> str:
        return f"<Game code={self.code} phase={self.phase}>"
