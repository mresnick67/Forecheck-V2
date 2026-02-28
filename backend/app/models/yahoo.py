from sqlalchemy import Column, String, DateTime, Float, ForeignKey
from datetime import datetime
import uuid

from app.database import Base


class YahooPlayerMapping(Base):
    __tablename__ = "yahoo_player_mapping"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    yahoo_player_id = Column(String(50), nullable=False, unique=True, index=True)
    yahoo_player_key = Column(String(100), nullable=True)
    name = Column(String(150), nullable=True)
    team_abbrev = Column(String(10), nullable=True)
    position = Column(String(20), nullable=True)
    match_method = Column(String(50), nullable=True)
    match_confidence = Column(Float, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlayerOwnershipSnapshot(Base):
    __tablename__ = "player_ownership_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    yahoo_player_id = Column(String(50), nullable=True, index=True)
    scope = Column(String(120), nullable=False, index=True)
    percent_owned = Column(Float, default=0.0)
    percent_started = Column(Float, default=0.0)
    percent_owned_change = Column(Float, default=0.0)
    as_of = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
