from sqlalchemy import Column, String, Integer, Date, DateTime, UniqueConstraint
from datetime import datetime
import uuid

from app.database import Base


class TeamWeekSchedule(Base):
    __tablename__ = "team_week_schedules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_abbrev = Column(String(10), nullable=False, index=True)
    season_id = Column(String(8), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    week_end = Column(Date, nullable=False)
    games_total = Column(Integer, default=0)
    light_games = Column(Integer, default=0)
    heavy_games = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "team_abbrev",
            "season_id",
            "week_start",
            name="uq_team_week_schedule",
        ),
    )
