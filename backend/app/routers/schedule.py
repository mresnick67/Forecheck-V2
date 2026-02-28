from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schedule import TeamWeekSchedule, WeeklyScheduleResponse
from app.services.season import current_season_id
from app.services.week_schedule import (
    build_weekly_remaining_counts,
    build_weekly_team_counts,
    build_weekly_team_days,
    get_week_day_summary,
    get_week_games,
    week_bounds_for_offset,
)


router = APIRouter(prefix="/schedule", tags=["Schedule"])


@router.get("/week", response_model=WeeklyScheduleResponse)
def get_week_schedule(
    db: Session = Depends(get_db),
    week_offset: int = Query(0, ge=-4, le=4),
):
    week_start, week_end = week_bounds_for_offset(week_offset)
    days = get_week_day_summary(db, week_start=week_start, week_end=week_end)
    games = get_week_games(db, week_start=week_start, week_end=week_end)
    team_counts = build_weekly_team_counts(games)
    remaining_map = build_weekly_remaining_counts(games)
    team_days_map = build_weekly_team_days(games)

    teams_payload = []
    for team_abbrev, counts in sorted(team_counts.items()):
        remaining = remaining_map.get(team_abbrev, {})
        game_days = team_days_map.get(team_abbrev, [])
        teams_payload.append(TeamWeekSchedule(
            team_abbrev=team_abbrev,
            season_id=current_season_id(),
            week_start=week_start,
            week_end=week_end,
            games_total=counts["games_total"],
            light_games=counts["light_games"],
            heavy_games=counts["heavy_games"],
            game_days=game_days,
            game_day_names=[day.strftime("%a") for day in game_days],
            remaining_games=remaining.get("remaining_games", 0),
            remaining_light_games=remaining.get("remaining_light_games", 0),
            remaining_heavy_games=remaining.get("remaining_heavy_games", 0),
        ))
    return {
        "week_start": week_start,
        "week_end": week_end,
        "days": days,
        "teams": teams_payload,
    }
