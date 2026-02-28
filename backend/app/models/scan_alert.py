from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, UniqueConstraint
from datetime import datetime
import uuid

from app.database import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False, index=True)
    run_at = Column(DateTime, default=datetime.utcnow, index=True)
    match_count = Column(Integer, default=0)
    error = Column(String(500), nullable=True)


class ScanAlertState(Base):
    __tablename__ = "scan_alert_state"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False, index=True)
    player_id = Column(String(36), ForeignKey("players.id"), nullable=False, index=True)
    is_current_match = Column(Boolean, default=False)
    last_matched_at = Column(DateTime, nullable=True)
    last_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("scan_id", "player_id", name="uq_scan_alert_state_scan_player"),
    )
