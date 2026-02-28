from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.player import Player
from app.models.sync_state import SyncState
from app.models.user import User
from app.services.analytics import AnalyticsService
from app.services.nhl_sync import (
    sync_all_game_logs,
    sync_game_center_game_logs,
    sync_player_game_log,
    sync_players,
    sync_schedule_for_dates,
)
from app.services.season import current_season_id
from app.services.week_schedule import update_current_week_schedule
from app.services.yahoo_oauth_service import has_yahoo_credentials
from app.services.yahoo_service import update_player_ownership

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()


def require_admin_key(request: Request) -> None:
    if not settings.admin_api_key:
        return
    api_key = request.headers.get("X-Admin-Key")
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _set_sync_state(db: Session, key: str, when: datetime | None = None) -> None:
    now = when or datetime.now(timezone.utc)
    state = db.query(SyncState).filter(SyncState.key == key).first()
    if state:
        state.last_run_at = now
    else:
        db.add(SyncState(key=key, last_run_at=now))
    db.commit()


@router.get("")
def admin_root(request: Request):
    require_admin_key(request)
    return {
        "name": "Forecheck v2 Admin",
        "status_endpoint": "/admin/status",
        "sync_endpoints": [
            "/admin/sync/players",
            "/admin/sync/game-logs",
            "/admin/sync/rolling-stats",
            "/admin/sync/weekly-schedule",
            "/admin/sync/ownership",
            "/admin/sync/pipeline",
        ],
    }


@router.get("/status")
def admin_status(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)
    states = db.query(SyncState).all()
    state_map = {state.key: state.last_run_at for state in states}

    yahoo_user = (
        db.query(User)
        .filter(
            User.yahoo_access_token.isnot(None),
            User.yahoo_refresh_token.isnot(None),
        )
        .first()
    )

    return {
        "app_mode": settings.app_mode,
        "enable_registration": settings.enable_registration,
        "run_sync_loop": settings.run_sync_loop,
        "nhl_sync_enabled": settings.nhl_sync_enabled,
        "nhl_sync_interval_minutes": settings.nhl_sync_interval_minutes,
        "current_season_id": current_season_id(),
        "last_player_sync_at": state_map.get("players"),
        "last_game_log_sync_at": state_map.get("nhl_game_logs"),
        "last_rolling_stats_at": state_map.get("rolling_stats"),
        "last_weekly_schedule_at": state_map.get("weekly_schedule"),
        "last_ownership_sync_at": state_map.get("yahoo_ownership"),
        "yahoo_enabled": settings.yahoo_enabled,
        "yahoo_connected": settings.yahoo_enabled and has_yahoo_credentials(yahoo_user),
        "server_time_utc": datetime.now(timezone.utc),
    }


@router.post("/player/refresh")
def refresh_player_logs(
    request: Request,
    player_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_key(request)
    target = db.query(Player).filter(Player.id == player_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    count = sync_player_game_log(db, target, season_id=current_season_id())
    _set_sync_state(db, "nhl_game_logs")
    return {"status": "ok", "updated": count}


@router.post("/sync/players")
def sync_players_endpoint(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)
    count = sync_players(db)
    _set_sync_state(db, "players")
    return {"status": "ok", "updated": count}


@router.post("/sync/game-logs")
def sync_game_logs_endpoint(
    request: Request,
    backfill_days: int | None = Query(default=None, ge=1, le=30),
    delay_seconds: float | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
):
    require_admin_key(request)
    count = sync_game_center_game_logs(
        db,
        season_id=current_season_id(),
        backfill_days=backfill_days,
        delay_seconds=delay_seconds,
    )
    _set_sync_state(db, "nhl_game_logs")
    return {"status": "ok", "updated": count}


@router.post("/sync/rolling-stats")
def sync_rolling_stats_endpoint(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)
    count = AnalyticsService.update_all_rolling_stats(db)
    _set_sync_state(db, "rolling_stats")
    return {"status": "ok", "updated": count}


@router.post("/sync/weekly-schedule")
def sync_weekly_schedule_endpoint(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)
    today = datetime.now(timezone.utc).date()
    dates = [datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)]
    for offset in range(0, 14):
        dates.append(datetime.combine(today + timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc))
    schedule_count = sync_schedule_for_dates(db, dates)
    update_current_week_schedule(db)
    _set_sync_state(db, "weekly_schedule")
    return {"status": "ok", "updated": schedule_count}


@router.post("/sync/ownership")
async def sync_ownership_endpoint(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)
    if not settings.yahoo_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yahoo integration disabled. Set YAHOO_ENABLED=true.",
        )

    user = db.query(User).filter(User.yahoo_access_token.isnot(None)).first()
    if not has_yahoo_credentials(user):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Yahoo OAuth credentials available",
        )

    updated = await update_player_ownership(db, user)
    _set_sync_state(db, "yahoo_ownership")
    return {"status": "ok", "updated": updated}


@router.post("/sync/pipeline")
async def sync_pipeline_endpoint(request: Request, db: Session = Depends(get_db)):
    require_admin_key(request)

    players_updated = sync_players(db)
    _set_sync_state(db, "players")

    today = datetime.now(timezone.utc).date()
    dates = [datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)]
    for offset in range(0, 14):
        dates.append(datetime.combine(today + timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc))
    schedule_updated = sync_schedule_for_dates(db, dates)
    update_current_week_schedule(db)
    _set_sync_state(db, "weekly_schedule")

    game_logs_updated = sync_all_game_logs(db, season_id=current_season_id())
    _set_sync_state(db, "nhl_game_logs")

    rolling_updated = AnalyticsService.update_all_rolling_stats(db)
    _set_sync_state(db, "rolling_stats")

    yahoo_updated = None
    if settings.yahoo_enabled:
        user = db.query(User).filter(User.yahoo_access_token.isnot(None)).first()
        if has_yahoo_credentials(user):
            yahoo_updated = await update_player_ownership(db, user)
            _set_sync_state(db, "yahoo_ownership")

    return {
        "status": "ok",
        "players_updated": players_updated,
        "weekly_schedule_updated": schedule_updated,
        "game_logs_updated": game_logs_updated,
        "rolling_stats_updated": rolling_updated,
        "yahoo_updated": yahoo_updated,
    }
