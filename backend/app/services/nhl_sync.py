from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from typing import Iterable, Optional, Union

from nhlpy import NHLClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.database import SessionLocal
from app.models.player import Player, PlayerGameStats
from app.models.scan import Scan
from app.models.user import User
from app.models.game import Game
from app.models.sync_state import SyncState
from app.models.sync_run import SyncRun, SyncCheckpoint
from app.services.analytics import AnalyticsService
from app.services.nhl_stats_api import (
    fetch_all_game_stats,
    fetch_goalie_game_stats,
    fetch_goalie_season_summaries,
    fetch_skater_game_stats,
    fetch_skater_game_stats_range,
    fetch_skater_season_summaries,
)
from app.services.nhl_roster_api import fetch_all_rosters
from app.services.scan_evaluator import ScanEvaluatorService
from app.services.season import current_season_id, season_id_for_date, current_game_type
from app.services.streamer_score_config import get_default_streamer_score_config
from app.services.yahoo_oauth_service import has_yahoo_credentials
from app.services.yahoo_service import update_player_ownership


logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class PlayerSnapshot:
    external_id: str
    name: str
    team: str
    position: str
    number: Optional[int]
    headshot_url: Optional[str]
    current_streamer_score: float
    ownership_percentage: float


def _client() -> NHLClient:
    return NHLClient()


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_team(value: Optional[str]) -> str:
    if not value:
        return "UNK"
    return value.strip()


def _normalize_position(value: Optional[str]) -> str:
    if not value:
        return "C"
    normalized = value.strip().upper()
    if normalized in {"C", "LW", "RW", "D", "G"}:
        return normalized
    if normalized in {"L", "LEFT", "LEFTWING", "LEFT_WING"}:
        return "LW"
    if normalized in {"R", "RIGHT", "RIGHTWING", "RIGHT_WING"}:
        return "RW"
    if normalized in {"LD", "RD"}:
        return "D"
    if normalized in {"CENTER", "CENTRE"}:
        return "C"
    if normalized in {"DEFENSE", "DEFENCE", "DEFENSEMAN", "DEFENCEMAN"}:
        return "D"
    if normalized in {"GOALIE", "GOALTENDER", "GK"}:
        return "G"
    if normalized in {"F", "FORWARD"}:
        return "C"
    return "C"


def _safe_int(value: Optional[object], default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _optional_int(value: Optional[object]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_int_from_entry(entry: dict, keys: Iterable[str]) -> tuple[Optional[int], bool]:
    for key in keys:
        if key in entry:
            return _optional_int(entry.get(key)), True
    return None, False


def _optional_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_float_from_entry(entry: dict, keys: Iterable[str]) -> tuple[Optional[float], bool]:
    for key in keys:
        if key in entry:
            return _optional_float(entry.get(key)), True
    return None, False


def _optional_bool_from_entry(entry: dict, keys: Iterable[str]) -> tuple[Optional[bool], bool]:
    for key in keys:
        if key in entry:
            value = entry.get(key)
            if isinstance(value, bool):
                return value, True
            if value is None:
                return None, True
            if isinstance(value, (int, float)):
                return bool(value), True
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "yes", "y", "1"}:
                    return True, True
                if normalized in {"false", "no", "n", "0"}:
                    return False, True
            return None, True
    return None, False


def _safe_float(value: Optional[object], default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_time_on_ice(value: Optional[object]) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parts = value.split(":")
        try:
            if len(parts) == 2:
                minutes, seconds = parts
                return float(minutes) * 60 + float(seconds)
            if len(parts) == 3:
                hours, minutes, seconds = parts
                return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
        except ValueError:
            return 0.0
    return 0.0


def _default_headshot_url(external_id: str) -> str:
    return f"https://assets.nhle.com/mugs/nhl/latest/{external_id}.png"


def _streamer_score_for_skater(
    position: str,
    points: float,
    games: float,
    shots: float,
    hits: float,
    blocks: float,
) -> float:
    games = games or 1.0
    ppg = points / games
    spg = shots / games
    hpg = hits / games
    bpg = blocks / games
    return AnalyticsService._calculate_streamer_score(
        position=position,
        ppg=ppg,
        spg=spg,
        ppp_pg=0.0,
        toi_pg=0.0,
        pm_pg=0.0,
        hpg=hpg,
        bpg=bpg,
        trend="stable",
        ownership=0.0,
        score_config=get_default_streamer_score_config(),
    )


def _streamer_score_for_goalie(save_pct: float, gaa: float, wins: float, games: float) -> float:
    games = games or 1.0
    return AnalyticsService._calculate_goalie_streamer_score(
        save_pct,
        gaa,
        int(wins),
        int(games),
        int(games),
        int(games),
        "stable",
        0.0,
        score_config=get_default_streamer_score_config(),
    )


def _skater_snapshot(entry: dict) -> Optional[PlayerSnapshot]:
    player_id = entry.get("playerId") or entry.get("id") or entry.get("player_id")
    name = entry.get("skaterFullName") or entry.get("fullName") or entry.get("name")
    team = entry.get("teamAbbrevs") or entry.get("teamAbbrev") or entry.get("team")
    if isinstance(team, list):
        team = team[0] if team else None
    position = entry.get("positionCode") or entry.get("position")
    number = entry.get("sweaterNumber") or entry.get("jerseyNumber")
    headshot = entry.get("headshot") or entry.get("headshotUrl")

    if not player_id or not name or not team:
        return None

    games = _safe_float(entry.get("gamesPlayed") or entry.get("games"))
    points = _safe_float(entry.get("points"))
    shots = _safe_float(entry.get("shots"))
    hits = _safe_float(entry.get("hits"))
    blocks = _safe_float(entry.get("blockedShots") or entry.get("blocks"))

    return PlayerSnapshot(
        external_id=str(player_id),
        name=name,
        team=_normalize_team(team),
        position=_normalize_position(position),
        number=_safe_int(number, default=0) or None,
        headshot_url=headshot or _default_headshot_url(str(player_id)),
        current_streamer_score=_streamer_score_for_skater(
            _normalize_position(position),
            points,
            games,
            shots,
            hits,
            blocks,
        ),
        ownership_percentage=0.0,
    )


def _goalie_snapshot(entry: dict) -> Optional[PlayerSnapshot]:
    player_id = entry.get("playerId") or entry.get("id") or entry.get("player_id")
    name = entry.get("goalieFullName") or entry.get("fullName") or entry.get("name")
    team = entry.get("teamAbbrevs") or entry.get("teamAbbrev") or entry.get("team")
    if isinstance(team, list):
        team = team[0] if team else None
    number = entry.get("sweaterNumber") or entry.get("jerseyNumber")
    headshot = entry.get("headshot") or entry.get("headshotUrl")

    if not player_id or not name or not team:
        return None

    games = _safe_float(entry.get("gamesPlayed") or entry.get("games"))
    wins = _safe_float(entry.get("wins"))
    save_pct = _safe_float(
        entry.get("savePct")
        or entry.get("savePctg")
        or entry.get("savePercentage")
    )
    gaa = _safe_float(entry.get("goalsAgainstAverage") or entry.get("gaa"))

    return PlayerSnapshot(
        external_id=str(player_id),
        name=name,
        team=_normalize_team(team),
        position="G",
        number=_safe_int(number, default=0) or None,
        headshot_url=headshot or _default_headshot_url(str(player_id)),
        current_streamer_score=_streamer_score_for_goalie(save_pct, gaa, wins, games),
        ownership_percentage=0.0,
    )


def _roster_snapshot(entry: dict) -> Optional[PlayerSnapshot]:
    player_id = entry.get("id") or entry.get("playerId") or entry.get("player_id")
    name = entry.get("fullName") or entry.get("name")
    if not name:
        first = entry.get("firstName")
        last = entry.get("lastName")
        if isinstance(first, dict):
            first = first.get("default") or first.get("en")
        if isinstance(last, dict):
            last = last.get("default") or last.get("en")
        if first or last:
            name = f"{first or ''} {last or ''}".strip()
    team = entry.get("teamAbbrev") or entry.get("team")
    position = entry.get("positionCode") or entry.get("position")
    number = entry.get("sweaterNumber") or entry.get("jerseyNumber")
    headshot = entry.get("headshot") or entry.get("headshotUrl")

    if not player_id or not name or not team:
        return None

    return PlayerSnapshot(
        external_id=str(player_id),
        name=name,
        team=_normalize_team(team),
        position=_normalize_position(position),
        number=_safe_int(number, default=0) or None,
        headshot_url=headshot or _default_headshot_url(str(player_id)),
        current_streamer_score=0.0,
        ownership_percentage=0.0,
    )


def sync_players(db: Session, season_id: Optional[str] = None) -> int:
    season_id = season_id or current_season_id()
    game_type = current_game_type()
    run = _start_sync_run(db, "players")

    try:
        roster_entries = fetch_all_rosters(season_id)
        roster_snapshots: dict[str, PlayerSnapshot] = {}
        for entry in roster_entries:
            snapshot = _roster_snapshot(entry)
            if snapshot:
                roster_snapshots[snapshot.external_id] = snapshot

        skaters = fetch_skater_season_summaries(season_id, game_type=game_type)
        goalies = fetch_goalie_season_summaries(season_id, game_type=game_type)

        snapshots: dict[str, PlayerSnapshot] = dict(roster_snapshots)
        for entry in skaters or []:
            snapshot = _skater_snapshot(entry)
            if not snapshot:
                continue
            existing = snapshots.get(snapshot.external_id)
            if existing:
                snapshots[snapshot.external_id] = PlayerSnapshot(
                    external_id=snapshot.external_id,
                    name=existing.name or snapshot.name,
                    team=existing.team or snapshot.team,
                    position=existing.position or snapshot.position,
                    number=existing.number or snapshot.number,
                    headshot_url=existing.headshot_url or snapshot.headshot_url,
                    current_streamer_score=snapshot.current_streamer_score,
                    ownership_percentage=existing.ownership_percentage,
                )
            else:
                snapshots[snapshot.external_id] = snapshot

        for entry in goalies or []:
            snapshot = _goalie_snapshot(entry)
            if not snapshot:
                continue
            existing = snapshots.get(snapshot.external_id)
            if existing:
                snapshots[snapshot.external_id] = PlayerSnapshot(
                    external_id=snapshot.external_id,
                    name=existing.name or snapshot.name,
                    team=existing.team or snapshot.team,
                    position=existing.position or snapshot.position,
                    number=existing.number or snapshot.number,
                    headshot_url=existing.headshot_url or snapshot.headshot_url,
                    current_streamer_score=snapshot.current_streamer_score,
                    ownership_percentage=existing.ownership_percentage,
                )
            else:
                snapshots[snapshot.external_id] = snapshot

        seen_external_ids = set()
        roster_external_ids = set(roster_snapshots.keys())
        has_roster_data = bool(roster_external_ids)
        updated = 0
        for snapshot in snapshots.values():
            seen_external_ids.add(snapshot.external_id)
            existing = db.query(Player).filter(Player.external_id == snapshot.external_id).first()
            if existing:
                existing.name = snapshot.name
                existing.team = snapshot.team
                existing.position = snapshot.position
                existing.number = snapshot.number
                existing.headshot_url = (
                    snapshot.headshot_url
                    or existing.headshot_url
                    or _default_headshot_url(snapshot.external_id)
                )
                # Preserve rolling streamer score and Yahoo ownership if already set.
                if snapshot.current_streamer_score > 0 and existing.current_streamer_score <= 0:
                    existing.current_streamer_score = snapshot.current_streamer_score
                if has_roster_data:
                    existing.is_active = snapshot.external_id in roster_external_ids
            else:
                db.add(Player(
                    external_id=snapshot.external_id,
                    name=snapshot.name,
                    team=snapshot.team,
                    position=snapshot.position,
                    number=snapshot.number,
                    headshot_url=snapshot.headshot_url or _default_headshot_url(snapshot.external_id),
                    current_streamer_score=snapshot.current_streamer_score,
                    ownership_percentage=snapshot.ownership_percentage,
                    is_active=(snapshot.external_id in roster_external_ids) if has_roster_data else True,
                ))
            updated += 1

        if has_roster_data:
            db.query(Player).filter(
                Player.external_id.isnot(None),
                ~Player.external_id.in_(roster_external_ids)
            ).update(
                {"is_active": False},
                synchronize_session=False,
            )
        elif seen_external_ids:
            db.query(Player).filter(Player.external_id.isnot(None), ~Player.external_id.in_(seen_external_ids)).update(
                {"is_active": False},
                synchronize_session=False,
            )
            db.query(Player).filter(Player.external_id.is_(None)).update(
                {"is_active": False},
                synchronize_session=False,
            )

        db.commit()
        _finish_sync_run(db, run, "success", updated)
        return updated
    except Exception as exc:
        db.rollback()
        _finish_sync_run(db, run, "failed", 0, error=str(exc)[:500])
        raise


def _get_sync_state(db: Session, key: str) -> Optional[SyncState]:
    return db.query(SyncState).filter(SyncState.key == key).first()


def _get_sync_checkpoint(db: Session, job: str) -> Optional[SyncCheckpoint]:
    return db.query(SyncCheckpoint).filter(SyncCheckpoint.job == job).first()


def _set_sync_state(db: Session, key: str, when: datetime) -> None:
    state = _get_sync_state(db, key)
    if state:
        state.last_run_at = when
    else:
        db.add(SyncState(key=key, last_run_at=when))
    db.commit()


def _start_sync_run(db: Session, job: str) -> SyncRun:
    run = SyncRun(job=job, status="running", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _finish_sync_run(db: Session, run: SyncRun, status: str, row_count: int = 0, error: Optional[str] = None) -> None:
    run.status = status
    run.row_count = row_count
    run.error = error
    run.finished_at = datetime.utcnow()
    db.commit()


def _set_sync_checkpoint(
    db: Session,
    job: str,
    season_id: Optional[str],
    game_type: Optional[int],
    last_game_date: Optional[datetime],
    last_game_id: Optional[str],
) -> None:
    checkpoint = db.query(SyncCheckpoint).filter(SyncCheckpoint.job == job).first()
    if checkpoint:
        checkpoint.season_id = season_id
        checkpoint.game_type = game_type
        checkpoint.last_game_date = last_game_date
        checkpoint.last_game_id = last_game_id
    else:
        db.add(SyncCheckpoint(
            job=job,
            season_id=season_id,
            game_type=game_type,
            last_game_date=last_game_date,
            last_game_id=last_game_id,
        ))
    db.commit()


def _extract_games(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if "games" in payload:
        return payload.get("games") or []
    if "gameWeek" in payload:
        games: list[dict] = []
        for day in payload.get("gameWeek") or []:
            games.extend(day.get("games") or [])
        return games
    if "dates" in payload:
        games = []
        for day in payload.get("dates") or []:
            games.extend(day.get("games") or [])
        return games
    return []


def _map_game_status(value: Optional[str]) -> str:
    if not value:
        return "scheduled"
    normalized = value.lower()
    if normalized in {"final", "off", "completed"}:
        return "final"
    if normalized in {"live", "in_progress", "critical"}:
        return "in_progress"
    if normalized in {"postponed", "ppd"}:
        return "postponed"
    return "scheduled"


def _extract_team_abbrev(payload: Optional[dict]) -> Optional[str]:
    if not payload:
        return None
    for key in ("abbrev", "teamAbbrev", "abbreviation", "triCode"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_game_id(entry: dict) -> Optional[str]:
    return entry.get("id") or entry.get("gameId") or entry.get("game_id")


def _game_ids_from_schedule(
    client: NHLClient,
    dates: Iterable[datetime],
    game_type: Optional[int] = None,
) -> list[dict]:
    results: list[dict] = []
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        try:
            payload = client.schedule.daily_schedule(date=date_str)
        except Exception as exc:
            logger.error("Schedule fetch failed for %s: %s", date_str, exc)
            continue
        for game in _extract_games(payload):
            game_id = _extract_game_id(game)
            if not game_id:
                continue
            status = _map_game_status(str(game.get("gameState") or game.get("gameStateId") or game.get("status")))
            if status != "final":
                continue
            if game_type is not None:
                scheduled_type = _safe_int(game.get("gameType") or game.get("gameTypeId"))
                if scheduled_type and scheduled_type != game_type:
                    continue
            home_team = game.get("homeTeam") or {}
            away_team = game.get("awayTeam") or {}
            results.append({
                "game_id": str(game_id),
                "game_type": _safe_int(game.get("gameType") or game.get("gameTypeId")),
                "game_date": _parse_date(game.get("startTimeUTC") or game.get("gameDate") or game.get("gameDateTime")),
                "home_team": _extract_team_abbrev(home_team),
                "away_team": _extract_team_abbrev(away_team),
            })
    return results


def _iter_boxscore_players(payload: dict, side: str) -> list[dict]:
    player_stats = payload.get("playerByGameStats") or {}
    team_stats = player_stats.get(f"{side}Team") or {}
    players: list[dict] = []
    for group_key in ("forwards", "defense", "defensemen", "goalies", "skaters", "roster"):
        group = team_stats.get(group_key) or []
        for player in group:
            if isinstance(player, dict):
                players.append(player)
    return players


def sync_schedule_for_dates(db: Session, dates: Iterable[datetime]) -> int:
    client = _client()
    updated = 0
    default_game_type = current_game_type()

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        payload = client.schedule.daily_schedule(date=date_str)
        for game in _extract_games(payload):
            external_id = game.get("id") or game.get("gameId") or game.get("game_id")
            if not external_id:
                continue
            home_team = game.get("homeTeam") or {}
            away_team = game.get("awayTeam") or {}
            home_abbr = home_team.get("abbrev") or home_team.get("teamAbbrev") or home_team.get("abbreviation")
            away_abbr = away_team.get("abbrev") or away_team.get("teamAbbrev") or away_team.get("abbreviation")
            start_time = game.get("startTimeUTC") or game.get("gameDate") or game.get("gameDateTime")
            status = game.get("gameState") or game.get("gameStateId") or game.get("status")

            game_date = _parse_date(start_time) or datetime.now(timezone.utc)
            season_id = season_id_for_date(game_date)
            game_type = _safe_int(game.get("gameType") or game.get("gameTypeId"), default=default_game_type)

            existing = db.query(Game).filter(Game.external_id == str(external_id)).first()
            if existing:
                existing.date = game_date
                existing.season_id = season_id
                existing.game_type = game_type
                existing.start_time_utc = game_date
                existing.home_team = _normalize_team(home_abbr)
                existing.away_team = _normalize_team(away_abbr)
                existing.home_score = _safe_int(home_team.get("score"), default=existing.home_score or 0)
                existing.away_score = _safe_int(away_team.get("score"), default=existing.away_score or 0)
                existing.status = _map_game_status(str(status))
                existing.status_source = "schedule"
            else:
                db.add(Game(
                    external_id=str(external_id),
                    date=game_date,
                    season_id=season_id,
                    game_type=game_type,
                    start_time_utc=game_date,
                    home_team=_normalize_team(home_abbr),
                    away_team=_normalize_team(away_abbr),
                    home_score=_safe_int(home_team.get("score"), default=None),
                    away_score=_safe_int(away_team.get("score"), default=None),
                    status=_map_game_status(str(status)),
                    status_source="schedule",
                ))
            updated += 1

    db.commit()
    return updated


def _sync_player_game_log_from_stats_api(db: Session, player: Player, season_id: str) -> int:
    game_type = current_game_type()
    if player.position == "G":
        goalie_stats = fetch_goalie_game_stats(
            season_id,
            player_id=str(player.external_id),
            game_type=game_type,
            limit=500,
        )
        if not goalie_stats:
            return 0
        updated = 0
        seen_game_ids: set[str] = set()
        for stats in goalie_stats:
            if stats.game_id in seen_game_ids:
                continue
            seen_game_ids.add(stats.game_id)
            game = db.query(Game).filter(Game.external_id == stats.game_id).first()
            if not game:
                if stats.is_home:
                    home_team = stats.team
                    away_team = stats.opponent
                else:
                    home_team = stats.opponent
                    away_team = stats.team

                game = Game(
                    external_id=stats.game_id,
                    date=stats.game_date,
                    season_id=season_id,
                    game_type=game_type,
                    start_time_utc=stats.game_date,
                    home_team=_normalize_team(home_team),
                    away_team=_normalize_team(away_team),
                    status="final",
                    status_source="stats_api",
                )
                db.add(game)
                db.flush()
            else:
                game.season_id = season_id
                game.game_type = game_type
                game.start_time_utc = game.start_time_utc or stats.game_date
                game.status_source = game.status_source or "stats_api"

            existing = db.query(PlayerGameStats).filter(
                PlayerGameStats.player_id == player.id,
                PlayerGameStats.game_id == game.id
            ).first()

            game_stats = existing or PlayerGameStats(
                player_id=player.id,
                game_id=game.id,
                date=stats.game_date,
                season_id=season_id,
                game_type=game_type,
                team_abbrev=stats.team,
                opponent_abbrev=stats.opponent,
                is_home=stats.is_home,
            )

            game_stats.season_id = season_id
            game_stats.game_type = game_type
            game_stats.team_abbrev = stats.team
            game_stats.opponent_abbrev = stats.opponent
            game_stats.is_home = stats.is_home
            game_stats.saves = stats.saves
            game_stats.shots_against = stats.shots_against
            game_stats.goals_against = stats.goals_against
            game_stats.wins = stats.wins
            game_stats.losses = stats.losses
            game_stats.overtime_losses = stats.ot_losses
            game_stats.shutouts = stats.shutouts
            game_stats.time_on_ice = stats.toi_seconds

            if not existing:
                db.add(game_stats)
            updated += 1

        db.commit()
        return updated

    skater_stats = fetch_skater_game_stats(
        season_id,
        player_id=str(player.external_id),
        game_type=game_type,
        limit=2000,
    )
    if not skater_stats:
        return 0

    updated = 0
    seen_game_ids: set[str] = set()
    for stats in skater_stats:
        if stats.game_id in seen_game_ids:
            continue
        seen_game_ids.add(stats.game_id)
        game = db.query(Game).filter(Game.external_id == stats.game_id).first()
        if not game:
            if stats.is_home:
                home_team = stats.team
                away_team = stats.opponent
            else:
                home_team = stats.opponent
                away_team = stats.team

            game = Game(
                external_id=stats.game_id,
                date=stats.game_date,
                season_id=season_id,
                game_type=game_type,
                start_time_utc=stats.game_date,
                home_team=_normalize_team(home_team),
                away_team=_normalize_team(away_team),
                status="final",
                status_source="stats_api",
            )
            db.add(game)
            db.flush()
        else:
            game.season_id = season_id
            game.game_type = game_type
            game.start_time_utc = game.start_time_utc or stats.game_date
            game.status_source = game.status_source or "stats_api"

        existing = db.query(PlayerGameStats).filter(
            PlayerGameStats.player_id == player.id,
            PlayerGameStats.game_id == game.id
        ).first()

        game_stats = existing or PlayerGameStats(
            player_id=player.id,
            game_id=game.id,
            date=stats.game_date,
            season_id=season_id,
            game_type=game_type,
            team_abbrev=stats.team,
            opponent_abbrev=stats.opponent,
            is_home=stats.is_home,
        )

        game_stats.season_id = season_id
        game_stats.game_type = game_type
        game_stats.team_abbrev = stats.team
        game_stats.opponent_abbrev = stats.opponent
        game_stats.is_home = stats.is_home
        game_stats.goals = stats.goals
        game_stats.assists = stats.assists
        game_stats.points = stats.points
        game_stats.shots = stats.shots
        game_stats.hits = stats.hits
        game_stats.blocks = stats.blocks
        game_stats.plus_minus = stats.plus_minus
        game_stats.pim = stats.pim
        game_stats.power_play_points = stats.pp_points
        game_stats.shorthanded_points = stats.sh_points
        game_stats.time_on_ice = stats.toi_seconds
        game_stats.takeaways = stats.takeaways
        game_stats.giveaways = stats.giveaways

        if not existing:
            db.add(game_stats)
        updated += 1

    db.commit()
    return updated


def _sync_player_game_log_from_game_center(
    db: Session,
    player: Player,
    season_id: str,
    delay_seconds: Optional[float] = None,
) -> int:
    client = _client()
    if client is None:
        return 0

    payload = client.stats.player_game_log(
        player_id=str(player.external_id),
        season_id=season_id,
        game_type=settings.nhl_game_type,
    )

    if isinstance(payload, dict):
        entries = payload.get("gameLog") or payload.get("data") or payload.get("games") or []
    else:
        entries = payload or []

    if not entries:
        return 0

    player_lookup = {str(player.external_id): player}
    updated_total = 0
    seen_game_ids: set[str] = set()
    for entry in entries:
        game_id = entry.get("gameId") or entry.get("id")
        if not game_id:
            continue
        game_id_str = str(game_id)
        if game_id_str in seen_game_ids:
            continue
        seen_game_ids.add(game_id_str)

        updated, _ = _sync_game_center_boxscore(
            db,
            player_lookup,
            game_id=game_id_str,
            season_id=season_id,
            game_type=current_game_type(),
            fallback_home=entry.get("teamAbbrev"),
            fallback_away=entry.get("opponentAbbrev"),
            fallback_date=_parse_date(entry.get("gameDate")),
        )
        updated_total += updated
        if updated:
            game = db.query(Game).filter(Game.external_id == game_id_str).first()
            if game:
                stats = db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == player.id,
                    PlayerGameStats.game_id == game.id,
                ).first()
                if stats:
                    _apply_stats_log_special_teams(stats, entry)

        delay = delay_seconds if delay_seconds is not None else settings.nhl_game_center_delay_seconds
        if delay > 0:
            time.sleep(delay)

    db.commit()
    return updated_total


def _season_start_date(season_id: str) -> datetime:
    if len(season_id) == 8 and season_id.isdigit():
        start_year = int(season_id[:4])
    else:
        start_year = datetime.now(timezone.utc).year
    return datetime(start_year, 9, 1, tzinfo=timezone.utc)


def sync_game_center_full_backfill(
    db: Session,
    season_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    delay_seconds: Optional[float] = None,
    reset_existing: bool = False,
) -> int:
    season_id = season_id or current_season_id()
    game_type = current_game_type()
    run = _start_sync_run(db, "nhl_game_logs")

    if reset_existing:
        deleted = db.query(PlayerGameStats).filter(
            PlayerGameStats.season_id == season_id,
            PlayerGameStats.game_type == game_type,
        ).delete(synchronize_session=False)
        db.commit()
        logger.info("Cleared %s existing game stat rows for season %s", deleted, season_id)

    start_date = start_date or _season_start_date(season_id)
    end_date = end_date or datetime.now(timezone.utc)
    current = datetime.combine(start_date.date(), datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date.date(), datetime.min.time(), tzinfo=timezone.utc)
    dates: list[datetime] = []
    while current <= end_dt:
        dates.append(current)
        current += timedelta(days=1)

    client = _client()
    if client is None:
        _finish_sync_run(db, run, "failed", 0, error="nhlpy client unavailable")
        return 0

    scheduled_games = _game_ids_from_schedule(client, dates, game_type=game_type)
    if not scheduled_games:
        _finish_sync_run(db, run, "success", 0)
        return 0

    deduped_games: list[dict] = []
    seen_game_ids: set[str] = set()
    for game in scheduled_games:
        game_id = game.get("game_id")
        if not game_id or game_id in seen_game_ids:
            continue
        seen_game_ids.add(game_id)
        deduped_games.append(game)

    players = db.query(Player).filter(Player.external_id.isnot(None)).all()
    player_lookup = {p.external_id: p for p in players}

    total_updated = 0
    latest_game_date: Optional[datetime] = None
    commit_every = max(settings.nhl_sync_commit_batch_size, 100)
    for idx, game in enumerate(deduped_games, start=1):
        game_id = game["game_id"]
        updated, game_date = _sync_game_center_boxscore(
            db,
            player_lookup,
            game_id=game_id,
            season_id=season_id,
            game_type=game_type,
            fallback_home=game.get("home_team"),
            fallback_away=game.get("away_team"),
            fallback_date=game.get("game_date"),
        )
        total_updated += updated
        if game_date and (latest_game_date is None or game_date > latest_game_date):
            latest_game_date = game_date
        if commit_every and total_updated % commit_every == 0:
            db.commit()
            logger.info("Committed %s game log rows (game center full backfill)", total_updated)
        delay = delay_seconds if delay_seconds is not None else settings.nhl_game_center_delay_seconds
        if delay > 0:
            time.sleep(delay)

    db.commit()
    _finish_sync_run(db, run, "success", total_updated)
    if latest_game_date is not None:
        _set_sync_checkpoint(
            db,
            "nhl_game_logs",
            season_id=season_id,
            game_type=game_type,
            last_game_date=latest_game_date,
            last_game_id=None,
        )
    return total_updated


def sync_player_game_log(db: Session, player: Player, season_id: Optional[str] = None) -> int:
    if not player.external_id:
        return 0
    season_id = season_id or current_season_id()
    return _sync_player_game_log_from_game_center(db, player, season_id)


def needs_game_log_sync(db: Session, player: Player) -> bool:
    if not player.external_id:
        return False
    latest = db.query(PlayerGameStats).filter(
        PlayerGameStats.player_id == player.id
    ).order_by(PlayerGameStats.date.desc()).first()
    if not latest:
        return True
    latest_date = latest.date
    if latest_date.tzinfo is None:
        latest_date = latest_date.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - latest_date
    return age.total_seconds() > settings.nhl_game_log_max_age_hours * 3600


def _apply_boxscore_skater_stats(stats: PlayerGameStats, entry: dict) -> None:
    goals = _safe_int(entry.get("goals"))
    assists = _safe_int(entry.get("assists"))
    points = _safe_int(entry.get("points"), default=goals + assists)

    shots = _safe_int(
        entry.get("shots")
        or entry.get("shotsOnGoal")
        or entry.get("shotsOnNet")
        or entry.get("sog")
        or entry.get("shotsOnGoalTotal")
    )

    stats.goals = goals
    stats.assists = assists
    stats.points = points
    stats.shots = shots
    stats.hits = _safe_int(entry.get("hits"))
    stats.blocks = _safe_int(entry.get("blockedShots") or entry.get("blocks"))
    stats.plus_minus = _safe_int(entry.get("plusMinus"))
    stats.pim = _safe_int(entry.get("pim") or entry.get("penaltyMinutes"))
    pp_points, pp_present = _optional_int_from_entry(entry, ["powerPlayPoints", "ppPoints"])
    if pp_present and pp_points is not None:
        stats.power_play_points = pp_points
    else:
        pp_goals, pp_goals_present = _optional_int_from_entry(entry, ["powerPlayGoals", "ppGoals", "ppg"])
        pp_assists, pp_assists_present = _optional_int_from_entry(entry, ["powerPlayAssists", "ppAssists", "ppa"])
        if (pp_goals_present or pp_assists_present) and (pp_goals is not None or pp_assists is not None):
            stats.power_play_points = (pp_goals or 0) + (pp_assists or 0)

    sh_points, sh_present = _optional_int_from_entry(
        entry, ["shorthandedPoints", "shPoints", "shortHandedPoints"]
    )
    if sh_present and sh_points is not None:
        stats.shorthanded_points = sh_points
    else:
        sh_goals, sh_goals_present = _optional_int_from_entry(
            entry, ["shortHandedGoals", "shGoals", "shg"]
        )
        sh_assists, sh_assists_present = _optional_int_from_entry(
            entry, ["shortHandedAssists", "shAssists", "sha"]
        )
        if (sh_goals_present or sh_assists_present) and (sh_goals is not None or sh_assists is not None):
            stats.shorthanded_points = (sh_goals or 0) + (sh_assists or 0)
    stats.time_on_ice = _parse_time_on_ice(entry.get("toi") or entry.get("timeOnIce"))
    stats.takeaways = _safe_int(entry.get("takeaways"))
    stats.giveaways = _safe_int(entry.get("giveaways"))
    stats.faceoff_wins = _safe_int(entry.get("faceoffWins"))

    faceoff_taken = _safe_int(
        entry.get("faceoffTaken")
        or entry.get("faceoffsTaken")
        or entry.get("faceoffAttempts")
    )
    if faceoff_taken:
        stats.faceoff_losses = max(faceoff_taken - stats.faceoff_wins, 0)


def _apply_stats_log_special_teams(stats: PlayerGameStats, entry: dict) -> None:
    pp_points, pp_present = _optional_int_from_entry(entry, ["powerPlayPoints", "ppPoints"])
    if pp_present and pp_points is not None:
        stats.power_play_points = pp_points

    sh_points, sh_present = _optional_int_from_entry(
        entry, ["shorthandedPoints", "shPoints", "shortHandedPoints"]
    )
    if sh_present and sh_points is not None:
        stats.shorthanded_points = sh_points


def _apply_boxscore_goalie_stats(stats: PlayerGameStats, entry: dict) -> None:
    saves, present = _optional_int_from_entry(entry, ["saves"])
    if present:
        stats.saves = saves
    shots_against, present = _optional_int_from_entry(entry, ["shotsAgainst", "shotsAgainstTotal"])
    if present:
        stats.shots_against = shots_against
    goals_against, present = _optional_int_from_entry(entry, ["goalsAgainst"])
    if present:
        stats.goals_against = goals_against
    save_pct, present = _optional_float_from_entry(entry, ["savePctg", "savePct", "savePercentage"])
    if present:
        stats.save_percentage = save_pct
    wins, present = _optional_int_from_entry(entry, ["wins"])
    if present:
        stats.wins = wins
    losses, present = _optional_int_from_entry(entry, ["losses"])
    if present:
        stats.losses = losses
    overtime_losses, present = _optional_int_from_entry(entry, ["otLosses", "otLossesTotal"])
    if present:
        stats.overtime_losses = overtime_losses
    decision = entry.get("decision")
    if decision is not None:
        stats.goalie_decision = str(decision).strip().upper() or None
        if stats.goalie_decision == "W":
            stats.wins = stats.wins if stats.wins is not None else 1
            stats.losses = stats.losses if stats.losses is not None else 0
            stats.overtime_losses = (
                stats.overtime_losses if stats.overtime_losses is not None else 0
            )
        elif stats.goalie_decision == "L":
            stats.wins = stats.wins if stats.wins is not None else 0
            stats.losses = stats.losses if stats.losses is not None else 1
            stats.overtime_losses = (
                stats.overtime_losses if stats.overtime_losses is not None else 0
            )
        elif stats.goalie_decision == "O":
            stats.wins = stats.wins if stats.wins is not None else 0
            stats.losses = stats.losses if stats.losses is not None else 0
            stats.overtime_losses = (
                stats.overtime_losses if stats.overtime_losses is not None else 1
            )
    starter, present = _optional_bool_from_entry(entry, ["starter"])
    if present:
        stats.goalie_starter = starter
    even_shots, present = _optional_int_from_entry(entry, ["evenStrengthShotsAgainst"])
    if present:
        stats.even_strength_shots_against = even_shots
    pp_shots, present = _optional_int_from_entry(entry, ["powerPlayShotsAgainst"])
    if present:
        stats.power_play_shots_against = pp_shots
    sh_shots, present = _optional_int_from_entry(entry, ["shorthandedShotsAgainst"])
    if present:
        stats.shorthanded_shots_against = sh_shots
    even_goals, present = _optional_int_from_entry(entry, ["evenStrengthGoalsAgainst"])
    if present:
        stats.even_strength_goals_against = even_goals
    pp_goals, present = _optional_int_from_entry(entry, ["powerPlayGoalsAgainst"])
    if present:
        stats.power_play_goals_against = pp_goals
    sh_goals, present = _optional_int_from_entry(entry, ["shorthandedGoalsAgainst"])
    if present:
        stats.shorthanded_goals_against = sh_goals
    if goals_against is not None:
        stats.shutouts = 1 if goals_against == 0 and stats.goalie_starter is True else 0
    time_on_ice = entry.get("toi") or entry.get("timeOnIce")
    if time_on_ice is not None:
        stats.time_on_ice = _parse_time_on_ice(time_on_ice)


def _sync_game_center_boxscore(
    db: Session,
    player_lookup: dict[str, Player],
    game_id: str,
    season_id: str,
    game_type: int,
    fallback_home: Optional[str] = None,
    fallback_away: Optional[str] = None,
    fallback_date: Optional[datetime] = None,
) -> tuple[int, Optional[datetime]]:
    client = _client()
    if client is None:
        return 0, None

    try:
        payload = client.game_center.boxscore(game_id)
    except Exception as exc:
        logger.error("Boxscore fetch failed for %s: %s", game_id, exc)
        return 0, None
    if not payload:
        return 0, None

    home_team_payload = payload.get("homeTeam") or payload.get("homeTeamInfo") or {}
    away_team_payload = payload.get("awayTeam") or payload.get("awayTeamInfo") or {}
    home_team = _extract_team_abbrev(home_team_payload) or fallback_home
    away_team = _extract_team_abbrev(away_team_payload) or fallback_away
    game_date = _parse_date(
        payload.get("gameDate")
        or payload.get("gameDateUTC")
        or payload.get("startTimeUTC")
    ) or fallback_date or datetime.now(timezone.utc)

    game = db.query(Game).filter(Game.external_id == str(game_id)).first()
    if not game:
        game = Game(
            external_id=str(game_id),
            date=game_date,
            season_id=season_id,
            game_type=game_type,
            start_time_utc=game_date,
            home_team=_normalize_team(home_team),
            away_team=_normalize_team(away_team),
            status="final",
            status_source="game_center",
        )
        db.add(game)
        db.flush()
    else:
        game.date = game.date or game_date
        game.season_id = season_id
        game.game_type = game_type
        game.start_time_utc = game.start_time_utc or game_date
        game.home_team = _normalize_team(home_team) if home_team else game.home_team
        game.away_team = _normalize_team(away_team) if away_team else game.away_team
        game.status = game.status or "final"
        game.status_source = game.status_source or "game_center"

    updated = 0
    for side in ("home", "away"):
        team_abbrev = home_team if side == "home" else away_team
        opponent_abbrev = away_team if side == "home" else home_team
        is_home = side == "home"

        for entry in _iter_boxscore_players(payload, side):
            player_id = entry.get("playerId") or entry.get("id") or entry.get("player_id")
            if not player_id:
                continue
            player = player_lookup.get(str(player_id))
            if not player:
                continue

            existing = db.query(PlayerGameStats).filter(
                PlayerGameStats.player_id == player.id,
                PlayerGameStats.game_id == game.id
            ).first()

            stats = existing or PlayerGameStats(
                player_id=player.id,
                game_id=game.id,
                date=game_date,
                season_id=season_id,
                game_type=game_type,
                team_abbrev=_normalize_team(team_abbrev),
                opponent_abbrev=_normalize_team(opponent_abbrev),
                is_home=is_home,
            )

            stats.date = game_date
            stats.season_id = season_id
            stats.game_type = game_type
            stats.team_abbrev = _normalize_team(team_abbrev)
            stats.opponent_abbrev = _normalize_team(opponent_abbrev)
            stats.is_home = is_home

            if player.position == "G":
                _apply_boxscore_goalie_stats(stats, entry)
            else:
                _apply_boxscore_skater_stats(stats, entry)

            if not existing:
                db.add(stats)
            updated += 1

    return updated, game_date


def sync_game_center_game_logs(
    db: Session,
    season_id: Optional[str] = None,
    backfill_days: Optional[int] = None,
    delay_seconds: Optional[float] = None,
) -> int:
    season_id = season_id or current_season_id()
    game_type = current_game_type()
    checkpoint = _get_sync_checkpoint(db, "nhl_game_logs")
    has_checkpoint = bool(checkpoint and checkpoint.last_game_date)
    if not has_checkpoint:
        logger.info(
            "No game log checkpoint found; bootstrapping full-season GameCenter sync from %s",
            _season_start_date(season_id).date().isoformat(),
        )

    run = _start_sync_run(db, "nhl_game_logs")

    end_date = datetime.now(timezone.utc).date()
    if has_checkpoint and checkpoint and checkpoint.last_game_date:
        start_date = checkpoint.last_game_date.date()
        # Allow callers to force a wider backfill window than the checkpoint.
        if backfill_days is not None:
            forced_start = end_date - timedelta(days=max(backfill_days, 0))
            if forced_start < start_date:
                start_date = forced_start
    else:
        start_date = _season_start_date(season_id).date()
    if start_date > end_date:
        start_date = end_date

    dates: list[datetime] = []
    current = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc)
    while current <= end_dt:
        dates.append(current)
        current += timedelta(days=1)

    client = _client()
    if client is None:
        _finish_sync_run(db, run, "failed", 0, error="nhlpy client unavailable")
        return 0

    scheduled_games = _game_ids_from_schedule(client, dates, game_type=game_type)
    if not scheduled_games:
        _finish_sync_run(db, run, "success", 0)
        return 0
    deduped_games: list[dict] = []
    seen_game_ids: set[str] = set()
    for game in scheduled_games:
        game_id = game.get("game_id")
        if not game_id or game_id in seen_game_ids:
            continue
        seen_game_ids.add(game_id)
        deduped_games.append(game)

    players = db.query(Player).filter(Player.external_id.isnot(None)).all()
    player_lookup = {p.external_id: p for p in players}

    total_updated = 0
    latest_game_date: Optional[datetime] = None
    for game in deduped_games:
        game_id = game["game_id"]
        updated, game_date = _sync_game_center_boxscore(
            db,
            player_lookup,
            game_id=game_id,
            season_id=season_id,
            game_type=game_type,
            fallback_home=game.get("home_team"),
            fallback_away=game.get("away_team"),
            fallback_date=game.get("game_date"),
        )
        total_updated += updated
        if game_date and (latest_game_date is None or game_date > latest_game_date):
            latest_game_date = game_date
        delay = delay_seconds if delay_seconds is not None else settings.nhl_game_center_delay_seconds
        if delay > 0:
            time.sleep(delay)

    db.commit()
    _finish_sync_run(db, run, "success", total_updated)
    if latest_game_date is not None:
        _set_sync_checkpoint(
            db,
            "nhl_game_logs",
            season_id=season_id,
            game_type=game_type,
            last_game_date=latest_game_date,
            last_game_id=None,
        )
    try:
        ppp_updated = sync_ppp_shp_from_stats_api(
            db,
            season_id=season_id,
            start_date=start_date,
            end_date=end_date,
            game_type=game_type,
        )
        logger.info("Patched %s PPP/SHP entries from stats API", ppp_updated)
    except Exception as exc:
        logger.error("PPP/SHP patch failed after GameCenter sync: %s", exc, exc_info=True)
    return total_updated


def sync_ppp_shp_from_stats_api(
    db: Session,
    season_id: Optional[str] = None,
    start_date: Optional[Union[datetime, date]] = None,
    end_date: Optional[Union[datetime, date]] = None,
    game_type: Optional[int] = None,
) -> int:
    season_id = season_id or current_season_id()
    game_type = game_type if game_type is not None else current_game_type()

    def _normalize_date(value: Optional[Union[datetime, date]]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        return None

    start_dt = _normalize_date(start_date)
    end_dt = _normalize_date(end_date)

    run = _start_sync_run(db, "ppp_shp_patch")
    try:
        skater_stats = fetch_skater_game_stats_range(
            season_id=season_id,
            start_date=start_dt,
            end_date=end_dt,
            game_type=game_type,
        )

        if not skater_stats:
            _finish_sync_run(db, run, "success", 0)
            return 0

        player_lookup = {
            str(p.external_id): p.id
            for p in db.query(Player).filter(Player.external_id.isnot(None)).all()
        }
        game_lookup = {
            g.external_id: g.id
            for g in db.query(Game).filter(
                Game.season_id == season_id,
                Game.game_type == game_type,
            ).all()
        }

        updated = 0
        commit_every = max(settings.nhl_sync_commit_batch_size, 200)
        for stats in skater_stats:
            player_id = player_lookup.get(stats.player_id)
            if not player_id:
                continue
            game_id = game_lookup.get(stats.game_id)
            if not game_id:
                continue
            game_stats = db.query(PlayerGameStats).filter(
                PlayerGameStats.player_id == player_id,
                PlayerGameStats.game_id == game_id,
            ).first()
            if not game_stats:
                continue
            game_stats.power_play_points = stats.pp_points
            game_stats.shorthanded_points = stats.sh_points
            updated += 1
            if commit_every and updated % commit_every == 0:
                db.commit()

        db.commit()
        _finish_sync_run(db, run, "success", updated)
        _set_sync_state(db, "ppp_shp_sync", datetime.now(timezone.utc))
        return updated
    except Exception as exc:
        db.rollback()
        _finish_sync_run(db, run, "failed", 0, error=str(exc)[:500])
        raise


def sync_all_game_logs(
    db: Session,
    season_id: Optional[str] = None,
    source_override: Optional[str] = None,
    backfill_days: Optional[int] = None,
    delay_seconds: Optional[float] = None,
) -> int:
    return sync_game_center_game_logs(
        db,
        season_id=season_id,
        backfill_days=backfill_days,
        delay_seconds=delay_seconds,
    )


def sync_all_game_logs_from_stats_api(
    db: Session,
    season_id: Optional[str] = None,
    reset_existing: bool = False,
) -> int:
    """
    Sync all player game logs using the NHL Stats API.

    This uses the stats API endpoints which include hits, blocks, saves, etc.
    that are missing from the web API game log endpoint.
    """
    season_id = season_id or current_season_id()
    game_type = current_game_type()
    run = _start_sync_run(db, "nhl_game_logs")

    commit_every = max(settings.nhl_sync_commit_batch_size, 100)

    if reset_existing:
        deleted = db.query(PlayerGameStats).filter(
            PlayerGameStats.season_id == season_id,
            PlayerGameStats.game_type == game_type,
        ).delete(synchronize_session=False)
        db.commit()
        logger.info(f"Cleared {deleted} existing game stat rows for season {season_id}")

    # Build a lookup of players by external_id
    players = db.query(Player).filter(
        Player.external_id.isnot(None),
        Player.is_active == True
    ).all()
    player_lookup = {p.external_id: p.id for p in players}
    logger.info(f"Found {len(player_lookup)} active players")

    count = 0
    seen_skater_keys: set[tuple[str, str]] = set()

    try:
        logger.info("Fetching all game stats from NHL Stats API...")
        skater_stats, goalie_stats = fetch_all_game_stats(season_id, game_type=game_type)
        logger.info(f"Fetched {len(skater_stats)} skater game records")
        logger.info(f"Fetched {len(goalie_stats)} goalie game records")

        for stats in skater_stats:
            player_id = player_lookup.get(stats.player_id)
            if not player_id:
                continue
            key = (player_id, stats.game_id)
            if key in seen_skater_keys:
                continue
            seen_skater_keys.add(key)

            # Find or create game
            game = db.query(Game).filter(Game.external_id == stats.game_id).first()
            if not game:
                if stats.is_home:
                    home_team = stats.team
                    away_team = stats.opponent
                else:
                    home_team = stats.opponent
                    away_team = stats.team

                game = Game(
                    external_id=stats.game_id,
                    date=stats.game_date,
                    season_id=season_id,
                    game_type=game_type,
                    start_time_utc=stats.game_date,
                    home_team=_normalize_team(home_team),
                    away_team=_normalize_team(away_team),
                    status="final",
                    status_source="stats_api",
                )
                db.add(game)
                db.flush()
            else:
                game.season_id = season_id
                game.game_type = game_type
                game.start_time_utc = game.start_time_utc or stats.game_date
                game.status_source = game.status_source or "stats_api"

            # Find or create player game stats
            existing = None
            if not reset_existing:
                existing = db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == player_id,
                    PlayerGameStats.game_id == game.id
                ).first()

            game_stats = existing or PlayerGameStats(
                player_id=player_id,
                game_id=game.id,
                date=stats.game_date,
                season_id=season_id,
                game_type=game_type,
                team_abbrev=stats.team,
                opponent_abbrev=stats.opponent,
                is_home=stats.is_home,
            )

            game_stats.season_id = season_id
            game_stats.game_type = game_type
            game_stats.team_abbrev = stats.team
            game_stats.opponent_abbrev = stats.opponent
            game_stats.is_home = stats.is_home
            # Update all stats including hits and blocks
            game_stats.goals = stats.goals
            game_stats.assists = stats.assists
            game_stats.points = stats.points
            game_stats.shots = stats.shots
            game_stats.hits = stats.hits
            game_stats.blocks = stats.blocks
            game_stats.plus_minus = stats.plus_minus
            game_stats.pim = stats.pim
            game_stats.power_play_points = stats.pp_points
            game_stats.shorthanded_points = stats.sh_points
            game_stats.time_on_ice = stats.toi_seconds
            game_stats.takeaways = stats.takeaways
            game_stats.giveaways = stats.giveaways

            if not existing:
                db.add(game_stats)
            count += 1
            if commit_every and count % commit_every == 0:
                db.commit()
                logger.info("Committed %s skater game stats", count)

        db.commit()
        logger.info(f"Synced {count} skater game stats")

    except OperationalError as exc:
        logger.error(f"Failed to sync skater game stats: {exc}", exc_info=True)
        db.rollback()
        _finish_sync_run(db, run, "failed", count, error=str(exc)[:500])
        raise
    except Exception as exc:
        logger.error(f"Failed to sync skater game stats: {exc}", exc_info=True)
        db.rollback()
        _finish_sync_run(db, run, "failed", count, error=str(exc)[:500])
        raise

    # Sync goalie game stats
    goalie_count = 0
    seen_goalie_keys: set[tuple[str, str]] = set()
    try:
        for stats in goalie_stats:
            player_id = player_lookup.get(stats.player_id)
            if not player_id:
                continue
            key = (player_id, stats.game_id)
            if key in seen_goalie_keys:
                continue
            seen_goalie_keys.add(key)

            # Find or create game
            game = db.query(Game).filter(Game.external_id == stats.game_id).first()
            if not game:
                if stats.is_home:
                    home_team = stats.team
                    away_team = stats.opponent
                else:
                    home_team = stats.opponent
                    away_team = stats.team

                game = Game(
                    external_id=stats.game_id,
                    date=stats.game_date,
                    season_id=season_id,
                    game_type=game_type,
                    start_time_utc=stats.game_date,
                    home_team=_normalize_team(home_team),
                    away_team=_normalize_team(away_team),
                    status="final",
                    status_source="stats_api",
                )
                db.add(game)
                db.flush()
            else:
                game.season_id = season_id
                game.game_type = game_type
                game.start_time_utc = game.start_time_utc or stats.game_date
                game.status_source = game.status_source or "stats_api"

            # Find or create player game stats
            existing = None
            if not reset_existing:
                existing = db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == player_id,
                    PlayerGameStats.game_id == game.id
                ).first()

            game_stats = existing or PlayerGameStats(
                player_id=player_id,
                game_id=game.id,
                date=stats.game_date,
                season_id=season_id,
                game_type=game_type,
                team_abbrev=stats.team,
                opponent_abbrev=stats.opponent,
                is_home=stats.is_home,
            )

            game_stats.season_id = season_id
            game_stats.game_type = game_type
            game_stats.team_abbrev = stats.team
            game_stats.opponent_abbrev = stats.opponent
            game_stats.is_home = stats.is_home
            # Update goalie stats
            game_stats.saves = stats.saves
            game_stats.shots_against = stats.shots_against
            game_stats.goals_against = stats.goals_against
            game_stats.wins = stats.wins
            game_stats.losses = stats.losses
            game_stats.overtime_losses = stats.ot_losses
            game_stats.shutouts = stats.shutouts
            game_stats.time_on_ice = stats.toi_seconds

            if not existing:
                db.add(game_stats)
            goalie_count += 1
            if commit_every and goalie_count % commit_every == 0:
                db.commit()
                logger.info("Committed %s goalie game stats", goalie_count)

        db.commit()
        logger.info(f"Synced {goalie_count} goalie game stats")

    except OperationalError as exc:
        logger.error(f"Failed to sync goalie game stats: {exc}", exc_info=True)
        db.rollback()
        _finish_sync_run(db, run, "failed", count + goalie_count, error=str(exc)[:500])
        raise
    except Exception as exc:
        logger.error(f"Failed to sync goalie game stats: {exc}", exc_info=True)
        db.rollback()
        _finish_sync_run(db, run, "failed", count + goalie_count, error=str(exc)[:500])
        raise

    total = count + goalie_count
    _finish_sync_run(db, run, "success", total)
    latest_date = db.query(Game.date).order_by(Game.date.desc()).first()
    _set_sync_checkpoint(
        db,
        "nhl_game_logs",
        season_id=season_id,
        game_type=game_type,
        last_game_date=latest_date[0] if latest_date else None,
        last_game_id=None,
    )
    return total


def sync_all() -> None:
    db = SessionLocal()
    try:
        season_id = current_season_id()
        sync_players(db, season_id=season_id)
        _set_sync_state(db, "players", datetime.now(timezone.utc))

        today = datetime.now(timezone.utc).date()
        dates = [datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)]
        for offset in range(0, 14):
            dates.append(datetime.combine(today + timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc))
        sync_schedule_for_dates(db, dates)
        from app.services.week_schedule import update_current_week_schedule
        update_current_week_schedule(db)
        _set_sync_state(db, "weekly_schedule", datetime.now(timezone.utc))
        _maybe_run_nightly_sync(db, season_id)
    finally:
        db.close()


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _maybe_run_nightly_sync(db: Session, season_id: str) -> None:
    now = datetime.now(timezone.utc)
    state = _get_sync_state(db, "nhl_game_logs")
    last_run = _normalize_utc(state.last_run_at) if state else None
    target_hour = settings.nhl_nightly_sync_hour_utc
    target_today = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    should_run = last_run is None or (now >= target_today and last_run < target_today)
    if should_run:
        logger.info("Starting initial sync bootstrap..." if last_run is None else "Starting nightly sync...")

        # 1. Sync all game logs
        game_log_count = sync_game_center_game_logs(db, season_id=season_id)
        logger.info(f"Synced {game_log_count} game log entries")
        _set_sync_state(db, "nhl_game_logs", now)

        # 2. Update rolling stats for all players
        try:
            rolling_run = _start_sync_run(db, "rolling_stats")
            rolling_stats_count = AnalyticsService.update_all_rolling_stats(db)
            logger.info(f"Updated {rolling_stats_count} rolling stats entries")
            _set_sync_state(db, "rolling_stats", now)
            _finish_sync_run(db, rolling_run, "success", rolling_stats_count)
        except Exception as exc:
            if "rolling_run" in locals():
                _finish_sync_run(db, rolling_run, "failed", 0, error=str(exc)[:500])
            logger.error(f"Failed to update rolling stats: {exc}", exc_info=True)

        # 2b. Refresh persisted scan counts so Discover/Scans stay populated.
        try:
            scan_refresh_run = _start_sync_run(db, "scan_counts")
            scan_rows = db.query(Scan).all()
            scan_count = ScanEvaluatorService.refresh_match_counts(
                db,
                scan_rows,
                stale_minutes=30,
                force=True,
            )
            _set_sync_state(db, "scan_counts", now)
            _finish_sync_run(db, scan_refresh_run, "success", scan_count)
            logger.info("Refreshed %s scan match counts", scan_count)
        except Exception as exc:
            if "scan_refresh_run" in locals():
                _finish_sync_run(db, scan_refresh_run, "failed", 0, error=str(exc)[:500])
            logger.error("Failed to refresh scan counts: %s", exc, exc_info=True)

        # 3. Update Yahoo ownership (if enabled and connected)
        if settings.yahoo_enabled:
            try:
                yahoo_run = _start_sync_run(db, "yahoo_ownership")
                yahoo_user = db.query(User).filter(
                    User.yahoo_access_token.isnot(None),
                    User.yahoo_refresh_token.isnot(None),
                ).first()
                if has_yahoo_credentials(yahoo_user):
                    import asyncio
                    updated = asyncio.run(update_player_ownership(db, yahoo_user))
                    logger.info(f"Updated Yahoo ownership for {updated} players")
                    _set_sync_state(db, "yahoo_ownership", now)
                    _finish_sync_run(db, yahoo_run, "success", updated)
                else:
                    _finish_sync_run(db, yahoo_run, "skipped", 0)
            except Exception as exc:
                if "yahoo_run" in locals():
                    _finish_sync_run(db, yahoo_run, "failed", 0, error=str(exc)[:500])
                logger.error(f"Failed to update Yahoo ownership: {exc}", exc_info=True)

        logger.info("Nightly sync completed")
    else:
        last_run_display = last_run.isoformat() if last_run else "None"
        logger.info(
            "Skipping nightly sync. now=%s target=%s last_run=%s",
            now.isoformat(),
            target_today.isoformat(),
            last_run_display,
        )


async def run_periodic_sync() -> None:
    logger.info("Starting periodic NHL sync task")
    while True:
        try:
            logger.debug("Running periodic sync...")
            await _run_sync_in_thread()
            logger.debug("Periodic sync completed")
        except Exception as exc:
            logger.error(f"Periodic sync failed: {exc}", exc_info=True)
        await _sleep_interval()


async def _run_sync_in_thread() -> None:
    import asyncio
    await asyncio.to_thread(sync_all)


async def _sleep_interval() -> None:
    import asyncio
    interval = max(settings.nhl_sync_interval_minutes, 5) * 60
    await asyncio.sleep(interval)
