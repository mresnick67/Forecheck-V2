from sqlalchemy import Column, String, DateTime
from datetime import datetime, timezone

from app.database import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    key = Column(String(100), primary_key=True)
    last_run_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
