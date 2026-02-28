from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.player import Player as PlayerModel, PlayerRollingStats as RollingStatsModel, PlayerGameStats as GameStatsModel
from app.models.team_week_schedule import TeamWeekSchedule
from app.models.game import Game as GameModel
from app.schemas.player import Player, PlayerWithStats, PlayerRollingStats, PlayerGameStats
from app.schemas.game import Game
from app.config import get_settings
from app.services.analytics import AnalyticsService
from app.services.nhl_sync import sync_player_game_log, needs_game_log_sync
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
