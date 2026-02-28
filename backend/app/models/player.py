from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class Position(str, enum.Enum):
    CENTER = "C"
    LEFT_WING = "LW"
    RIGHT_WING = "RW"
    DEFENSEMAN = "D"
    GOALIE = "G"


class TrendDirection(str, enum.Enum):
    HOT = "hot"
    COLD = "cold"
    STABLE = "stable"


class Player(Base):
    __tablename__ = "players"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(50), unique=True, nullable=True)  # NHL API ID
    name = Column(String(100), nullable=False, index=True)
    team = Column(String(10), nullable=False, index=True)
    position = Column(String(5), nullable=False)
    number = Column(Integer, nullable=True)
    headshot_url = Column(String(500), nullable=True)
    current_streamer_score = Column(Float, default=0.0)
    ownership_percentage = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game_stats = relationship("PlayerGameStats", back_populates="player")
    rolling_stats = relationship("PlayerRollingStats", back_populates="player")


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    game_id = Column(String(36), ForeignKey("games.id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    season_id = Column(String(8), nullable=True, index=True)
    game_type = Column(Integer, nullable=True, index=True)
    team_abbrev = Column(String(10), nullable=True)
    opponent_abbrev = Column(String(10), nullable=True)
    is_home = Column(Boolean, nullable=True)

    # Skater stats
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    points = Column(Integer, default=0)
    shots = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    blocks = Column(Integer, default=0)
    plus_minus = Column(Integer, default=0)
    pim = Column(Integer, default=0)
    power_play_points = Column(Integer, default=0)
    shorthanded_points = Column(Integer, default=0)
    time_on_ice = Column(Float, default=0.0)  # in seconds
    faceoff_wins = Column(Integer, default=0)
    faceoff_losses = Column(Integer, default=0)
    takeaways = Column(Integer, default=0)
    giveaways = Column(Integer, default=0)

    # Goalie stats
    saves = Column(Integer, nullable=True)
    goals_against = Column(Integer, nullable=True)
    shots_against = Column(Integer, nullable=True)
    save_percentage = Column(Float, nullable=True)
    wins = Column(Integer, nullable=True)
    losses = Column(Integer, nullable=True)
    overtime_losses = Column(Integer, nullable=True)
    shutouts = Column(Integer, nullable=True)
    goalie_decision = Column(String(2), nullable=True)
    goalie_starter = Column(Boolean, nullable=True)
    even_strength_shots_against = Column(Integer, nullable=True)
    power_play_shots_against = Column(Integer, nullable=True)
    shorthanded_shots_against = Column(Integer, nullable=True)
    even_strength_goals_against = Column(Integer, nullable=True)
    power_play_goals_against = Column(Integer, nullable=True)
    shorthanded_goals_against = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    player = relationship("Player", back_populates="game_stats")
    game = relationship("Game", back_populates="player_stats")

    __table_args__ = (
        UniqueConstraint("player_id", "game_id", name="uq_player_game_stats_player_game"),
    )


class StatWindow(str, enum.Enum):
    LAST_5 = "L5"
    LAST_10 = "L10"
    LAST_20 = "L20"
    SEASON = "Season"


class PlayerRollingStats(Base):
    __tablename__ = "player_rolling_stats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    window = Column(String(10), nullable=False, index=True)  # L5, L10, L20, Season
    season_id = Column(String(8), nullable=True, index=True)
    game_type = Column(Integer, nullable=True, index=True)
    window_size = Column(Integer, nullable=True)
    games_played = Column(Integer, default=0)
    goalie_games_started = Column(Integer, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)
    last_game_date = Column(DateTime, nullable=True)

    # Per-game averages
    goals_per_game = Column(Float, default=0.0)
    assists_per_game = Column(Float, default=0.0)
    points_per_game = Column(Float, default=0.0)
    shots_per_game = Column(Float, default=0.0)
    hits_per_game = Column(Float, default=0.0)
    blocks_per_game = Column(Float, default=0.0)
    plus_minus_per_game = Column(Float, default=0.0)
    pim_per_game = Column(Float, default=0.0)
    power_play_points_per_game = Column(Float, default=0.0)
    shorthanded_points_per_game = Column(Float, default=0.0)
    time_on_ice_per_game = Column(Float, default=0.0)

    # Totals
    total_goals = Column(Integer, default=0)
    total_assists = Column(Integer, default=0)
    total_points = Column(Integer, default=0)
    total_shots = Column(Integer, default=0)
    total_hits = Column(Integer, default=0)
    total_blocks = Column(Integer, default=0)
    total_plus_minus = Column(Integer, default=0)
    total_pim = Column(Integer, default=0)
    total_power_play_points = Column(Integer, default=0)
    total_shorthanded_points = Column(Integer, default=0)

    # Goalie totals
    total_saves = Column(Integer, default=0)
    total_shots_against = Column(Integer, default=0)
    total_goals_against = Column(Integer, default=0)

    # Goalie stats
    save_percentage = Column(Float, nullable=True)
    goals_against_average = Column(Float, nullable=True)
    goalie_wins = Column(Integer, nullable=True)
    goalie_shutouts = Column(Integer, nullable=True)

    # Trends
    trend_direction = Column(String(10), default="stable")
    temperature_tag = Column(String(10), default="stable")
    streamer_score = Column(Float, default=0.0)

    # Relationships
    player = relationship("Player", back_populates="rolling_stats")

    # Unique constraint for player + window
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "window",
            "season_id",
            "game_type",
            name="uq_player_rolling_stats_scope",
        ),
        {"sqlite_autoincrement": True},
    )
