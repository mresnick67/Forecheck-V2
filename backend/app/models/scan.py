from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Null for preset scans
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    position_filter = Column(String(5), nullable=True)
    is_preset = Column(Boolean, default=False)
    is_followed = Column(Boolean, default=False)
    alerts_enabled = Column(Boolean, default=False)
    last_evaluated = Column(DateTime, nullable=True)
    match_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="scans")
    rules = relationship("ScanRule", back_populates="scan", cascade="all, delete-orphan")


class ScanRule(Base):
    __tablename__ = "scan_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False)
    stat = Column(String(50), nullable=False)  # goals, assists, points, etc.
    comparator = Column(String(10), nullable=False)  # >, >=, <, <=, =
    value = Column(Float, nullable=False)
    window = Column(String(10), nullable=False)  # L5, L10, L20, Season
    compare_window = Column(String(10), nullable=True)  # Optional compare window for deltas
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scan = relationship("Scan", back_populates="rules")


class ScanPreference(Base):
    __tablename__ = "scan_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False, index=True)
    is_hidden = Column(Boolean, default=False)
    is_followed = Column(Boolean, default=False)
    alerts_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "scan_id", name="uq_scan_preferences_user_scan"),
    )
