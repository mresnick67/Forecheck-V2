from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class Position(str, Enum):
    CENTER = "C"
    LEFT_WING = "LW"
    RIGHT_WING = "RW"
    DEFENSEMAN = "D"
    GOALIE = "G"


class TrendDirection(str, Enum):
    HOT = "hot"
    COLD = "cold"
    STABLE = "stable"


class StatWindow(str, Enum):
    LAST_5 = "L5"
    LAST_10 = "L10"
    LAST_20 = "L20"
    SEASON = "Season"


class PlayerBase(BaseModel):
    name: str
    team: str
    position: str
    number: Optional[int] = None
    headshot_url: Optional[str] = None


class PlayerCreate(PlayerBase):
    external_id: Optional[str] = None
    current_streamer_score: float = 0.0
    ownership_percentage: float = 0.0


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    team: Optional[str] = None
    position: Optional[str] = None
    number: Optional[int] = None
    headshot_url: Optional[str] = None
    current_streamer_score: Optional[float] = None
    ownership_percentage: Optional[float] = None


class Player(PlayerBase):
    id: str
    current_streamer_score: float
    ownership_percentage: float
    is_active: bool
    created_at: datetime
    weekly_games: Optional[int] = None
    weekly_light_games: Optional[int] = None
    weekly_heavy_games: Optional[int] = None

    class Config:
        from_attributes = True


class PlayerGameStatsBase(BaseModel):
    team_abbrev: Optional[str] = None
    opponent_abbrev: Optional[str] = None
    is_home: Optional[bool] = None
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    hits: int = 0
    blocks: int = 0
    takeaways: int = 0
    giveaways: int = 0
    plus_minus: int = 0
    pim: int = 0
    power_play_points: int = 0
    shorthanded_points: int = 0
    time_on_ice: float = 0.0
    faceoff_wins: int = 0
    faceoff_losses: int = 0
    # Goalie stats
    saves: Optional[int] = None
    goals_against: Optional[int] = None
    shots_against: Optional[int] = None
    save_percentage: Optional[float] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    overtime_losses: Optional[int] = None
    shutouts: Optional[int] = None
    goalie_decision: Optional[str] = None
    goalie_starter: Optional[bool] = None
    even_strength_shots_against: Optional[int] = None
    power_play_shots_against: Optional[int] = None
    shorthanded_shots_against: Optional[int] = None
    even_strength_goals_against: Optional[int] = None
    power_play_goals_against: Optional[int] = None
    shorthanded_goals_against: Optional[int] = None


class PlayerGameStatsCreate(PlayerGameStatsBase):
    player_id: str
    game_id: str
    date: datetime


class PlayerGameStats(PlayerGameStatsBase):
    id: str
    player_id: str
    game_id: str
    date: datetime
    season_id: Optional[str] = None
    game_type: Optional[int] = None

    class Config:
        from_attributes = True


class PlayerRollingStats(BaseModel):
    id: str
    player_id: str
    window: str
    season_id: Optional[str] = None
    game_type: Optional[int] = None
    window_size: Optional[int] = None
    games_played: int
    goalie_games_started: Optional[int] = None
    computed_at: datetime
    last_game_date: Optional[datetime] = None

    # Per-game averages
    goals_per_game: float
    assists_per_game: float
    points_per_game: float
    shots_per_game: float
    hits_per_game: float
    blocks_per_game: float
    plus_minus_per_game: float
    pim_per_game: float
    power_play_points_per_game: float
    shorthanded_points_per_game: float
    time_on_ice_per_game: float

    # Totals
    total_goals: int
    total_assists: int
    total_points: int
    total_shots: int
    total_hits: int
    total_blocks: int
    total_plus_minus: int
    total_pim: int
    total_power_play_points: int
    total_shorthanded_points: int

    # Goalie totals
    total_saves: Optional[int] = None
    total_shots_against: Optional[int] = None
    total_goals_against: Optional[int] = None

    # Goalie stats
    save_percentage: Optional[float] = None
    goals_against_average: Optional[float] = None
    goalie_wins: Optional[int] = None
    goalie_shutouts: Optional[int] = None

    # Trends
    trend_direction: str
    temperature_tag: str
    streamer_score: float

    class Config:
        from_attributes = True


class PlayerWithStats(Player):
    rolling_stats: Optional[dict[str, PlayerRollingStats]] = None  # keyed by window
    recent_games: Optional[List[PlayerGameStats]] = None
