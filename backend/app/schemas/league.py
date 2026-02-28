from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from enum import Enum


class LeagueType(str, Enum):
    CATEGORIES = "categories"
    POINTS = "points"


class LeagueBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    league_type: str
    scoring_weights: Dict[str, float] = {}


class LeagueCreate(LeagueBase):
    pass


class LeagueUpdate(BaseModel):
    name: Optional[str] = None
    league_type: Optional[str] = None
    scoring_weights: Optional[Dict[str, float]] = None
    is_active: Optional[bool] = None


class League(LeagueBase):
    id: str
    user_id: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
