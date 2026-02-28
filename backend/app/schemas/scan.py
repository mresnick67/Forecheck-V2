from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class StatType(str, Enum):
    GOALS = "goals"
    ASSISTS = "assists"
    POINTS = "points"
    SHOTS = "shots"
    HITS = "hits"
    BLOCKS = "blocks"
    PLUS_MINUS = "plus_minus"
    PIM = "pim"
    POWER_PLAY_POINTS = "power_play_points"
    SHORTHANDED_POINTS = "shorthanded_points"
    TIME_ON_ICE = "time_on_ice"
    TIME_ON_ICE_DELTA = "time_on_ice_delta"
    SAVE_PERCENTAGE = "save_percentage"
    GOALS_AGAINST_AVERAGE = "goals_against_average"
    SAVES_PER_GAME = "saves_per_game"
    SHOOTING_PERCENTAGE = "shooting_percentage"
    WINS = "wins"
    SHUTOUTS = "shutouts"
    GOALIE_STARTS = "goalie_starts"
    OWNERSHIP_PERCENTAGE = "ownership_percentage"
    STREAMER_SCORE = "streamer_score"
    B2B_START_OPPORTUNITY = "b2b_start_opportunity"


class Comparator(str, Enum):
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="


class StatWindow(str, Enum):
    LAST_5 = "L5"
    LAST_10 = "L10"
    LAST_20 = "L20"
    SEASON = "Season"


class ScanRuleBase(BaseModel):
    stat: str
    comparator: str
    value: float
    window: str
    compare_window: Optional[str] = None


class ScanRuleCreate(ScanRuleBase):
    pass


class ScanRule(ScanRuleBase):
    id: str

    class Config:
        from_attributes = True


class ScanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = ""
    position_filter: Optional[str] = None


class ScanCreate(ScanBase):
    rules: List[ScanRuleCreate]
    alerts_enabled: bool = False


class ScanPreview(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = ""
    position_filter: Optional[str] = None
    rules: List[ScanRuleCreate]


class ScanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[List[ScanRuleCreate]] = None
    is_followed: Optional[bool] = None
    is_hidden: Optional[bool] = None
    alerts_enabled: Optional[bool] = None
    position_filter: Optional[str] = None


class Scan(ScanBase):
    id: str
    user_id: Optional[str] = None
    is_preset: bool
    is_followed: bool
    is_hidden: bool = False
    alerts_enabled: bool
    last_evaluated: Optional[datetime] = None
    match_count: int
    rules: List[ScanRule]
    created_at: datetime

    class Config:
        from_attributes = True


# Note: ScanWithResults is not needed - evaluate endpoint returns List[Player] directly
