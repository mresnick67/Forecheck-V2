from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, asc, desc, func
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.player import Player as PlayerModel, PlayerRollingStats as RollingStatsModel, PlayerGameStats as GameStatsModel
from app.models.scan import Scan as ScanModel
from app.models.team_week_schedule import TeamWeekSchedule
from app.models.game import Game as GameModel
from app.schemas.player import (
    ExplorePlayer,
    Player,
    PlayerWithStats,
    PlayerRollingStats,
    PlayerGameStats,
    PlayerSignals,
    PlayerSignalScan,
)
from app.schemas.game import Game
from app.config import get_settings
from app.services.analytics import AnalyticsService
from app.services.nhl_sync import sync_player_game_log, needs_game_log_sync
from app.services.scan_evaluator import ScanEvaluatorService
from app.services.season import current_season_id, current_game_type
from app.services.week_schedule import current_week_bounds

router = APIRouter(prefix="/players", tags=["Players"])
settings = get_settings()


def _weekly_schedule_map(db: Session) -> dict[str, TeamWeekSchedule]:
    week_start, _ = current_week_bounds()
    rows = db.query(TeamWeekSchedule).filter(
        TeamWeekSchedule.week_start == week_start,
        TeamWeekSchedule.season_id == current_season_id(),
    ).all()
    return {row.team_abbrev: row for row in rows}


def _player_payload(player: PlayerModel, weekly_map: dict[str, TeamWeekSchedule]) -> dict:
    payload = Player.model_validate(player).model_dump()
    schedule = weekly_map.get(player.team)
    if schedule:
        payload["weekly_games"] = schedule.games_total
        payload["weekly_light_games"] = schedule.light_games
        payload["weekly_heavy_games"] = schedule.heavy_games
    return payload


@router.get("", response_model=List[Player])
async def get_players(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    position: Optional[str] = None,
    team: Optional[str] = None,
    sort_by: str = Query("streamer_score", enum=["streamer_score", "name", "team", "ownership"]),
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    """Get list of players with optional filtering."""
    query = db.query(PlayerModel).filter(PlayerModel.is_active == True)

    # Apply filters
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            (PlayerModel.name.ilike(search_term)) |
            (PlayerModel.team.ilike(search_term))
        )

    if position:
        query = query.filter(PlayerModel.position == position)

    if team:
        query = query.filter(PlayerModel.team == team)

    # Apply sorting
    if sort_by == "streamer_score":
        query = query.order_by(desc(PlayerModel.current_streamer_score))
    elif sort_by == "name":
        query = query.order_by(PlayerModel.name)
    elif sort_by == "team":
        query = query.order_by(PlayerModel.team)
    elif sort_by == "ownership":
        query = query.order_by(desc(PlayerModel.ownership_percentage))

    players = query.offset(offset).limit(limit).all()
    weekly_map = _weekly_schedule_map(db)
    return [_player_payload(player, weekly_map) for player in players]


@router.get("/explore", response_model=List[ExplorePlayer])
async def explore_players(
    db: Session = Depends(get_db),
    window: str = Query("L10", description="Stat window: L5, L10, L20, Season"),
    search: Optional[str] = None,
    position: Optional[str] = Query(None, description="C, LW, RW, D, G"),
    team: Optional[str] = None,
    min_streamer_score: Optional[float] = Query(None, ge=0, le=100),
    min_ownership: Optional[float] = Query(None, ge=0, le=100),
    max_ownership: Optional[float] = Query(None, ge=0, le=100),
    min_games_played: int = Query(1, ge=0, le=82),
    min_weekly_games: int = Query(0, ge=0, le=7),
    min_weekly_light_games: int = Query(0, ge=0, le=7),
    sort_by: str = Query(
        "window_streamer_score",
        enum=[
            "window_streamer_score",
            "season_streamer_score",
            "ownership",
            "name",
            "team",
            "points",
            "shots",
            "hits",
            "blocks",
            "toi",
            "save_pct",
            "gaa",
            "wins",
            "games_played",
            "weekly_games",
            "weekly_light_games",
        ],
    ),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    limit: int = Query(120, ge=1, le=250),
    offset: int = Query(0, ge=0),
):
    season_id = current_season_id()
    game_type = current_game_type()
    week_start, _ = current_week_bounds()

    query = (
        db.query(PlayerModel, RollingStatsModel, TeamWeekSchedule)
        .join(
            RollingStatsModel,
            and_(
                RollingStatsModel.player_id == PlayerModel.id,
                RollingStatsModel.window == window,
                RollingStatsModel.season_id == season_id,
                RollingStatsModel.game_type == game_type,
            ),
        )
        .outerjoin(
            TeamWeekSchedule,
            and_(
                TeamWeekSchedule.team_abbrev == PlayerModel.team,
                TeamWeekSchedule.season_id == season_id,
                TeamWeekSchedule.week_start == week_start,
            ),
        )
        .filter(
            PlayerModel.is_active == True,
            RollingStatsModel.games_played >= min_games_played,
        )
    )

    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            PlayerModel.name.ilike(search_term) | PlayerModel.team.ilike(search_term)
        )
    if position:
        query = query.filter(PlayerModel.position == position)
    if team:
        query = query.filter(PlayerModel.team == team)
    if min_streamer_score is not None:
        query = query.filter(RollingStatsModel.streamer_score >= min_streamer_score)
    if min_ownership is not None:
        query = query.filter(PlayerModel.ownership_percentage >= min_ownership)
    if max_ownership is not None:
        query = query.filter(PlayerModel.ownership_percentage <= max_ownership)

    weekly_games_expr = func.coalesce(TeamWeekSchedule.games_total, 0)
    weekly_light_expr = func.coalesce(TeamWeekSchedule.light_games, 0)
    if min_weekly_games > 0:
        query = query.filter(weekly_games_expr >= min_weekly_games)
    if min_weekly_light_games > 0:
        query = query.filter(weekly_light_expr >= min_weekly_light_games)

    sort_expr = {
        "window_streamer_score": RollingStatsModel.streamer_score,
        "season_streamer_score": PlayerModel.current_streamer_score,
        "ownership": PlayerModel.ownership_percentage,
        "name": PlayerModel.name,
        "team": PlayerModel.team,
        "points": RollingStatsModel.points_per_game,
        "shots": RollingStatsModel.shots_per_game,
        "hits": RollingStatsModel.hits_per_game,
        "blocks": RollingStatsModel.blocks_per_game,
        "toi": RollingStatsModel.time_on_ice_per_game,
        "save_pct": RollingStatsModel.save_percentage,
        "gaa": RollingStatsModel.goals_against_average,
        "wins": RollingStatsModel.goalie_wins,
        "games_played": RollingStatsModel.games_played,
        "weekly_games": weekly_games_expr,
        "weekly_light_games": weekly_light_expr,
    }.get(sort_by, RollingStatsModel.streamer_score)

    if sort_order == "asc":
        query = query.order_by(asc(sort_expr), asc(PlayerModel.name))
    else:
        query = query.order_by(desc(sort_expr), asc(PlayerModel.name))

    rows = query.offset(offset).limit(limit).all()
    results: list[ExplorePlayer] = []
    for player, rolling, schedule in rows:
        payload = Player.model_validate(player).model_dump()
        payload["weekly_games"] = schedule.games_total if schedule else 0
        payload["weekly_light_games"] = schedule.light_games if schedule else 0
        payload["weekly_heavy_games"] = schedule.heavy_games if schedule else 0
        payload.update(
            {
                "window": rolling.window,
                "window_streamer_score": rolling.streamer_score,
                "games_played": rolling.games_played,
                "goalie_games_started": rolling.goalie_games_started,
                "points_per_game": rolling.points_per_game,
                "shots_per_game": rolling.shots_per_game,
                "hits_per_game": rolling.hits_per_game,
                "blocks_per_game": rolling.blocks_per_game,
                "time_on_ice_per_game": rolling.time_on_ice_per_game,
                "save_percentage": rolling.save_percentage,
                "goals_against_average": rolling.goals_against_average,
                "goalie_wins": rolling.goalie_wins,
            }
        )
        results.append(ExplorePlayer(**payload))
    return results


@router.get("/top-streamers", response_model=List[Player])
async def get_top_streamers(
    db: Session = Depends(get_db),
    position: Optional[str] = None,
    limit: int = Query(10, le=50),
):
    """Get top streamers by streamer score."""
    query = db.query(PlayerModel).filter(PlayerModel.is_active == True)

    if position:
        query = query.filter(PlayerModel.position == position)

    players = query.order_by(desc(PlayerModel.current_streamer_score)).limit(limit).all()
    weekly_map = _weekly_schedule_map(db)
    return [_player_payload(player, weekly_map) for player in players]


@router.get("/trending")
async def get_trending_players(
    db: Session = Depends(get_db),
    window: str = Query("L5", description="Stat window: L5, L10, L20, Season"),
    limit: int = Query(10, le=500),
):
    """
    Get trending players grouped by trend direction (hot/cold).

    Returns players whose recent performance differs significantly from their
    previous performance, indicating they are trending up (hot) or down (cold).
    """
    # Get rolling stats with trend data
    stats = (
        db.query(RollingStatsModel)
        .join(PlayerModel, RollingStatsModel.player_id == PlayerModel.id)
        .filter(
            PlayerModel.is_active == True,
            RollingStatsModel.window == window,
            RollingStatsModel.season_id == current_season_id(),
            RollingStatsModel.game_type == current_game_type(),
            RollingStatsModel.games_played >= 3,  # Need enough games for trend
        )
        .all()
    )

    weekly_map = _weekly_schedule_map(db)

    # Group by trend direction
    hot_players = []
    cold_players = []

    for stat in stats:
        player = db.query(PlayerModel).filter(PlayerModel.id == stat.player_id).first()
        if not player:
            continue

        player_data = {
            "id": player.id,
            "name": player.name,
            "team": player.team,
            "position": player.position,
            "headshot_url": player.headshot_url,
            "current_streamer_score": player.current_streamer_score,
            "ownership_percentage": player.ownership_percentage,
            "trend_direction": stat.trend_direction,
            "games_played": stat.games_played,
            "points_per_game": stat.points_per_game,
            "shots_per_game": stat.shots_per_game,
            "hits_per_game": stat.hits_per_game,
            "blocks_per_game": stat.blocks_per_game,
            # Goalie stats
            "save_percentage": stat.save_percentage,
            "goals_against_average": stat.goals_against_average,
            "goalie_wins": stat.goalie_wins,
        }
        schedule = weekly_map.get(player.team)
        if schedule:
            player_data["weekly_games"] = schedule.games_total
            player_data["weekly_light_games"] = schedule.light_games
            player_data["weekly_heavy_games"] = schedule.heavy_games

        if stat.trend_direction == "hot":
            hot_players.append(player_data)
        elif stat.trend_direction == "cold":
            cold_players.append(player_data)

    # Sort by streamer score within each group
    hot_players.sort(key=lambda x: x["current_streamer_score"], reverse=True)
    cold_players.sort(key=lambda x: x["current_streamer_score"], reverse=True)

    return {
        "window": window,
        "hot": hot_players[:limit],
        "cold": cold_players[:limit],
        "hot_count": len(hot_players),
        "cold_count": len(cold_players),
    }


@router.get("/temperature")
async def get_temperature_players(
    db: Session = Depends(get_db),
    window: str = Query("L5", description="Stat window: L5, L10, L20, Season"),
    limit: int = Query(10, le=500),
):
    """Get hot/cold players based on absolute L5 performance thresholds."""
    stats = (
        db.query(RollingStatsModel)
        .join(PlayerModel, RollingStatsModel.player_id == PlayerModel.id)
        .filter(
            PlayerModel.is_active == True,
            RollingStatsModel.window == window,
            RollingStatsModel.season_id == current_season_id(),
            RollingStatsModel.game_type == current_game_type(),
            RollingStatsModel.games_played >= 3,
        )
        .all()
    )

    weekly_map = _weekly_schedule_map(db)

    hot_players = []
    cold_players = []

    for stat in stats:
        player = db.query(PlayerModel).filter(PlayerModel.id == stat.player_id).first()
        if not player:
            continue

        player_data = {
            "id": player.id,
            "name": player.name,
            "team": player.team,
            "position": player.position,
            "headshot_url": player.headshot_url,
            "current_streamer_score": player.current_streamer_score,
            "ownership_percentage": player.ownership_percentage,
            "trend_direction": stat.temperature_tag,
            "games_played": stat.games_played,
            "points_per_game": stat.points_per_game,
            "shots_per_game": stat.shots_per_game,
            "hits_per_game": stat.hits_per_game,
            "blocks_per_game": stat.blocks_per_game,
            "save_percentage": stat.save_percentage,
            "goals_against_average": stat.goals_against_average,
            "goalie_wins": stat.goalie_wins,
        }
        schedule = weekly_map.get(player.team)
        if schedule:
            player_data["weekly_games"] = schedule.games_total
            player_data["weekly_light_games"] = schedule.light_games
            player_data["weekly_heavy_games"] = schedule.heavy_games

        if stat.temperature_tag == "hot":
            hot_players.append(player_data)
        elif stat.temperature_tag == "cold":
            cold_players.append(player_data)

    hot_players.sort(key=lambda x: x["current_streamer_score"], reverse=True)
    cold_players.sort(key=lambda x: x["current_streamer_score"], reverse=True)

    return {
        "window": window,
        "hot": hot_players[:limit],
        "cold": cold_players[:limit],
        "hot_count": len(hot_players),
        "cold_count": len(cold_players),
    }


@router.get("/rolling-stats", response_model=List[PlayerRollingStats])
async def get_rolling_stats(
    db: Session = Depends(get_db),
    window: str = Query(..., description="Stat window, e.g. L5, L10, L20, Season"),
    limit: int = Query(200, le=500),
    offset: int = 0,
):
    """Get rolling stats for all active players in a window."""
    stats = (
        db.query(RollingStatsModel)
        .join(PlayerModel, RollingStatsModel.player_id == PlayerModel.id)
        .filter(
            PlayerModel.is_active == True,
            RollingStatsModel.window == window,
            RollingStatsModel.season_id == current_season_id(),
            RollingStatsModel.game_type == current_game_type(),
        )
        .order_by(desc(RollingStatsModel.streamer_score))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return stats


@router.get("/{player_id}", response_model=PlayerWithStats)
async def get_player(
    player_id: str,
    db: Session = Depends(get_db),
):
    """Get player details with stats."""
    player = db.query(PlayerModel).filter(PlayerModel.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get rolling stats for all windows
    rolling_stats_list = db.query(RollingStatsModel).filter(
        RollingStatsModel.player_id == player_id,
        RollingStatsModel.season_id == current_season_id(),
        RollingStatsModel.game_type == current_game_type(),
    ).all()

    rolling_stats_dict = {}
    for stats in rolling_stats_list:
        rolling_stats_dict[stats.window] = PlayerRollingStats.model_validate(stats)

    # Get recent game stats
    recent_games = db.query(GameStatsModel).filter(
        GameStatsModel.player_id == player_id
    ).order_by(desc(GameStatsModel.date)).limit(10).all()

    weekly_map = _weekly_schedule_map(db)
    payload = _player_payload(player, weekly_map)

    return PlayerWithStats(
        **payload,
        rolling_stats=rolling_stats_dict,
        recent_games=[PlayerGameStats.model_validate(g) for g in recent_games],
    )


@router.get("/{player_id}/signals", response_model=PlayerSignals)
async def get_player_signals(
    player_id: str,
    db: Session = Depends(get_db),
):
    """Get player detail signals used by the PWA detail header."""
    player = db.query(PlayerModel).filter(PlayerModel.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    l5_stats = db.query(RollingStatsModel).filter(
        RollingStatsModel.player_id == player_id,
        RollingStatsModel.window == "L5",
        RollingStatsModel.season_id == current_season_id(),
        RollingStatsModel.game_type == current_game_type(),
    ).first()

    # Ensure preset scans exist before matching.
    from app.routers.scans import ensure_preset_scans
    ensure_preset_scans(db)

    presets = db.query(ScanModel).filter(ScanModel.is_preset == True).all()
    preset_matches: list[PlayerSignalScan] = []
    for scan in presets:
        results = ScanEvaluatorService.evaluate(db, scan)
        if any(result.id == player_id for result in results):
            preset_matches.append(PlayerSignalScan(id=scan.id, name=scan.name))

    preset_matches.sort(key=lambda item: item.name)

    return PlayerSignals(
        trend_direction=l5_stats.trend_direction if l5_stats else None,
        temperature_tag=l5_stats.temperature_tag if l5_stats else None,
        preset_matches=preset_matches,
    )


@router.get("/{player_id}/stats/{window}", response_model=PlayerRollingStats)
async def get_player_stats(
    player_id: str,
    window: str,
    db: Session = Depends(get_db),
):
    """Get player rolling stats for a specific window."""
    player = db.query(PlayerModel).filter(PlayerModel.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if settings.nhl_player_on_demand_sync and needs_game_log_sync(db, player):
        try:
            sync_player_game_log(db, player)
        except Exception as exc:
            print(f"Failed to sync game log for player {player_id}: {exc}")

    stats = db.query(RollingStatsModel).filter(
        RollingStatsModel.player_id == player_id,
        RollingStatsModel.window == window,
        RollingStatsModel.season_id == current_season_id(),
        RollingStatsModel.game_type == current_game_type(),
    ).first()

    if not stats:
        try:
            stats = AnalyticsService.compute_rolling_stats(db, player, window)
            db.add(stats)
            db.commit()
            db.refresh(stats)
        except Exception as exc:
            print(f"Failed to compute rolling stats for player {player_id}: {exc}")
            stats = AnalyticsService._empty_rolling_stats(
                player.id,
                window,
                current_season_id(),
                current_game_type(),
            )

    return stats


@router.get("/{player_id}/games", response_model=List[PlayerGameStats])
async def get_player_games(
    player_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(10, le=50),
):
    """Get player's recent game stats."""
    player = db.query(PlayerModel).filter(PlayerModel.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if settings.nhl_player_on_demand_sync and needs_game_log_sync(db, player):
        try:
            sync_player_game_log(db, player)
        except Exception as exc:
            print(f"Failed to sync game log for player {player_id}: {exc}")

    games = db.query(GameStatsModel).filter(
        GameStatsModel.player_id == player_id
    ).order_by(desc(GameStatsModel.date)).limit(limit).all()

    return games


@router.get("/{player_id}/schedule", response_model=List[Game])
async def get_player_schedule(
    player_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(5, le=20),
):
    """Get player's upcoming games."""
    player = db.query(PlayerModel).filter(PlayerModel.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    games = db.query(GameModel).filter(
        ((GameModel.home_team == player.team) | (GameModel.away_team == player.team)),
        GameModel.status == "scheduled",
        GameModel.date >= datetime.utcnow(),
    ).order_by(GameModel.date).limit(limit).all()

    return games
