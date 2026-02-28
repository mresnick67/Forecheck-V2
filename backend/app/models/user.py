from datetime import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, default="")

    is_active = Column(Boolean, default=True)
    scans_created = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    refresh_token_hash = Column(Text, nullable=True)
    refresh_token_expires_at = Column(DateTime, nullable=True)
    refresh_token_last_used_at = Column(DateTime, nullable=True)

    yahoo_access_token = Column(Text, nullable=True)
    yahoo_refresh_token = Column(Text, nullable=True)
    yahoo_token_expires_at = Column(DateTime, nullable=True)
    yahoo_user_guid = Column(String(100), nullable=True)

    scans = relationship("Scan", back_populates="user")
    scan_preferences = relationship("ScanPreference")
    leagues = relationship("League", back_populates="user")
