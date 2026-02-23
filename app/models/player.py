"""Player model."""
import enum
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class PlayerRole(str, enum.Enum):
    """Roles a player can have in a game."""

    PLAYER = "player"
    SPECTATOR = "spectator"


class Player(db.Model):
    """Represents a participant (player or spectator) in a game session."""

    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("game_id", "display_name", name="uq_game_display_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[PlayerRole] = mapped_column(
        Enum(PlayerRole, values_callable=lambda e: [v.value for v in e]),
        nullable=False,
        default=PlayerRole.PLAYER,
    )
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # 0-indexed join order, drives judge rotation; spectator is excluded from rotation
    join_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    game: Mapped["Game"] = relationship(  # type: ignore[name-defined]
        "Game", foreign_keys=[game_id], back_populates="players"
    )
    created_cards: Mapped[list["Card"]] = relationship(  # type: ignore[name-defined]
        "Card", foreign_keys="Card.creator_id", back_populates="creator", lazy="select"
    )
    held_cards: Mapped[list["Card"]] = relationship(  # type: ignore[name-defined]
        "Card", foreign_keys="Card.holder_id", back_populates="holder", lazy="select"
    )
    submissions: Mapped[list["Submission"]] = relationship(  # type: ignore[name-defined]
        "Submission", back_populates="player", lazy="select"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="voter", lazy="select"
    )

    @property
    def is_spectator(self) -> bool:
        """Return True if this participant is a spectator."""
        return self.role == PlayerRole.SPECTATOR

    def __repr__(self) -> str:
        return f"<Player name={self.display_name} role={self.role}>"
