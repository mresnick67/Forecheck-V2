from sqlalchemy import Column, String, Integer, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class GameStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINAL = "final"
    POSTPONED = "postponed"


class Game(Base):
    __tablename__ = "games"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(50), unique=True, nullable=True)  # NHL API ID
    date = Column(DateTime, nullable=False, index=True)
    season_id = Column(String(8), nullable=True, index=True)
    game_type = Column(Integer, nullable=True, index=True)
    start_time_utc = Column(DateTime, nullable=True)
    end_time_utc = Column(DateTime, nullable=True)
    home_team = Column(String(10), nullable=False, index=True)
    away_team = Column(String(10), nullable=False, index=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    status = Column(String(20), default="scheduled")
    status_source = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    player_stats = relationship("PlayerGameStats", back_populates="game")
