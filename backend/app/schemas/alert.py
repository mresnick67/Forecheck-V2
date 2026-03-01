from datetime import datetime

from pydantic import BaseModel


class ScanAlertFeedItem(BaseModel):
    scan_id: str
    scan_name: str
    player_id: str
    player_name: str
    team: str
    position: str
    headshot_url: str | None = None
    current_streamer_score: float
    detected_at: datetime


class ScanAlertSummaryItem(BaseModel):
    scan_id: str
    scan_name: str
    alerts_enabled: bool
    new_matches: int
    match_count: int
    last_evaluated: datetime | None = None
