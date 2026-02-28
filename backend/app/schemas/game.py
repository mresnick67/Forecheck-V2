from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


class GameStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINAL = "final"
    POSTPONED = "postponed"


class GameBase(BaseModel):
    date: datetime
    home_team: str
    away_team: str
    status: str = "scheduled"
    season_id: Optional[str] = None
    game_type: Optional[int] = None
    start_time_utc: Optional[datetime] = None

    @validator("date", "start_time_utc", pre=True)
    def _ensure_utc_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class GameCreate(GameBase):
    external_id: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class GameUpdate(BaseModel):
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: Optional[str] = None


class Game(GameBase):
    id: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
