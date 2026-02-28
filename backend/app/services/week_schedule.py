from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.team_week_schedule import TeamWeekSchedule
from app.services.season import current_season_id, current_game_type


EASTERN_TZ = ZoneInfo("America/New_York")
LIGHT_TEAM_THRESHOLD = 14


def current_week_bounds(now: datetime | None = None) -> tuple[date, date]:
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(EASTERN_TZ)
    week_start = now_et.date() - timedelta(days=now_et.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def week_bounds_for_offset(offset: int = 0, now: datetime | None = None) -> tuple[date, date]:
    week_start, week_end = current_week_bounds(now)
    if offset:
        delta = timedelta(days=7 * offset)
        week_start += delta
        week_end += delta
    return week_start, week_end


def week_bounds_to_utc(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    start_et = datetime.combine(week_start, time.min, tzinfo=EASTERN_TZ)
    end_et = datetime.combine(week_end, time.max, tzinfo=EASTERN_TZ)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def _game_date_et(game_date: datetime) -> date:
    if game_date.tzinfo is None:
        game_date = game_date.replace(tzinfo=timezone.utc)
    return game_date.astimezone(EASTERN_TZ).date()


def _collect_day_team_map(games: Iterable[Game]) -> dict[date, set[str]]:
    day_teams: dict[date, set[str]] = defaultdict(set)
    for game in games:
        game_day = _game_date_et(game.date)
        if game.home_team:
            day_teams[game_day].add(game.home_team)
        if game.away_team:
            day_teams[game_day].add(game.away_team)
    return day_teams


def build_weekly_team_counts(games: Iterable[Game]) -> dict[str, dict[str, int]]:
    day_teams = _collect_day_team_map(games)
    light_days = {day for day, teams in day_teams.items() if len(teams) < LIGHT_TEAM_THRESHOLD}

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {
        "games_total": 0,
        "light_games": 0,
        "heavy_games": 0,
    })

    for game in games:
        game_day = _game_date_et(game.date)
        is_light = game_day in light_days
        for team in (game.home_team, game.away_team):
            if not team:
                continue
            counts[team]["games_total"] += 1
            if is_light:
                counts[team]["light_games"] += 1
            else:
                counts[team]["heavy_games"] += 1

    return counts


def build_weekly_team_days(games: Iterable[Game]) -> dict[str, list[date]]:
    team_days: dict[str, set[date]] = defaultdict(set)
    for game in games:
        game_day = _game_date_et(game.date)
        for team in (game.home_team, game.away_team):
            if not team:
                continue
            team_days[team].add(game_day)

    return {team: sorted(days) for team, days in team_days.items()}


def build_weekly_remaining_counts(games: Iterable[Game], today: date | None = None) -> dict[str, dict[str, int]]:
    if today is None:
        today = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()

    day_teams = _collect_day_team_map(games)
    light_days = {day for day, teams in day_teams.items() if len(teams) < LIGHT_TEAM_THRESHOLD}

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {
        "remaining_games": 0,
        "remaining_light_games": 0,
        "remaining_heavy_games": 0,
    })

    for game in games:
        game_day = _game_date_et(game.date)
        if game_day < today:
            continue
        is_light = game_day in light_days
        for team in (game.home_team, game.away_team):
            if not team:
                continue
            counts[team]["remaining_games"] += 1
            if is_light:
                counts[team]["remaining_light_games"] += 1
            else:
                counts[team]["remaining_heavy_games"] += 1

    return counts


def get_week_day_summary(
    db: Session,
    week_start: date | None = None,
    week_end: date | None = None,
    season_id: str | None = None,
    game_type: int | None = None,
) -> list[dict]:
    season_id = season_id or current_season_id()
    game_type = game_type if game_type is not None else current_game_type()
    week_start, week_end = (week_start, week_end) if week_start and week_end else current_week_bounds()
    start_utc, end_utc = week_bounds_to_utc(week_start, week_end)

    games = (
        db.query(Game)
        .filter(
            Game.season_id == season_id,
            Game.game_type == game_type,
            Game.date >= start_utc,
            Game.date <= end_utc,
        )
        .all()
    )

    day_teams = _collect_day_team_map(games)
    summaries = []
    current = week_start
    while current <= week_end:
        teams_playing = len(day_teams.get(current, set()))
        summaries.append({
            "date": current,
            "teams_playing": teams_playing,
            "is_light": teams_playing < LIGHT_TEAM_THRESHOLD,
        })
        current += timedelta(days=1)
    return summaries


def get_week_games(
    db: Session,
    week_start: date | None = None,
    week_end: date | None = None,
    season_id: str | None = None,
    game_type: int | None = None,
) -> list[Game]:
    season_id = season_id or current_season_id()
    game_type = game_type if game_type is not None else current_game_type()
    week_start, week_end = (week_start, week_end) if week_start and week_end else current_week_bounds()
    start_utc, end_utc = week_bounds_to_utc(week_start, week_end)

    return (
        db.query(Game)
        .filter(
            Game.season_id == season_id,
            Game.game_type == game_type,
            Game.date >= start_utc,
            Game.date <= end_utc,
        )
        .all()
    )


def update_current_week_schedule(db: Session, now: datetime | None = None) -> int:
    season_id = current_season_id()
    game_type = current_game_type()
    week_start, week_end = current_week_bounds(now)
    start_utc, end_utc = week_bounds_to_utc(week_start, week_end)

    games = (
        db.query(Game)
        .filter(
            Game.season_id == season_id,
            Game.game_type == game_type,
            Game.date >= start_utc,
            Game.date <= end_utc,
        )
        .all()
    )

    team_counts = build_weekly_team_counts(games)
    updated = 0
    for team, counts in team_counts.items():
        existing = db.query(TeamWeekSchedule).filter(
            TeamWeekSchedule.team_abbrev == team,
            TeamWeekSchedule.season_id == season_id,
            TeamWeekSchedule.week_start == week_start,
        ).first()
        if existing:
            existing.week_end = week_end
            existing.games_total = counts["games_total"]
            existing.light_games = counts["light_games"]
            existing.heavy_games = counts["heavy_games"]
        else:
            db.add(TeamWeekSchedule(
                team_abbrev=team,
                season_id=season_id,
                week_start=week_start,
                week_end=week_end,
                games_total=counts["games_total"],
                light_games=counts["light_games"],
                heavy_games=counts["heavy_games"],
            ))
        updated += 1

    db.commit()
    return updated
