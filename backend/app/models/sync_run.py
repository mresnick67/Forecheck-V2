from sqlalchemy import Column, String, DateTime, Integer
from datetime import datetime
import uuid

from app.database import Base


class SyncCheckpoint(Base):
    __tablename__ = "sync_checkpoints"

    job = Column(String(100), primary_key=True)
    season_id = Column(String(8), nullable=True)
    game_type = Column(Integer, nullable=True)
    last_game_date = Column(DateTime, nullable=True)
    last_game_id = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    row_count = Column(Integer, default=0)
    error = Column(String(500), nullable=True)
