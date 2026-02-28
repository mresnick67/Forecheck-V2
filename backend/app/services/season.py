from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings


def season_id_for_date(date: datetime) -> str:
    year = date.year
    start_year = year if date.month >= 9 else year - 1
    return f"{start_year}{start_year + 1}"


def current_season_id(now: Optional[datetime] = None) -> str:
    settings = get_settings()
    if settings.nhl_season:
        return settings.nhl_season
    now = now or datetime.now(timezone.utc)
    return season_id_for_date(now)


def current_game_type() -> int:
    settings = get_settings()
    return settings.nhl_game_type
