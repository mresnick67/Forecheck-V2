from datetime import date
from typing import List

from pydantic import BaseModel


class WeekDaySummary(BaseModel):
    date: date
    teams_playing: int
    is_light: bool


class TeamWeekSchedule(BaseModel):
    team_abbrev: str
    season_id: str
    week_start: date
    week_end: date
    games_total: int
    light_games: int
    heavy_games: int
    game_days: List[date] = []
    game_day_names: List[str] = []
    remaining_games: int = 0
    remaining_light_games: int = 0
    remaining_heavy_games: int = 0

    class Config:
        from_attributes = True


class WeeklyScheduleResponse(BaseModel):
    week_start: date
    week_end: date
    days: List[WeekDaySummary]
    teams: List[TeamWeekSchedule]
