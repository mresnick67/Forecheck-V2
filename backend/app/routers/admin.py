from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.player import Player, PlayerGameStats
from app.models.scan import Scan
from app.models.sync_run import SyncCheckpoint, SyncRun
from app.models.sync_state import SyncState
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.analytics import AnalyticsService
from app.services.nhl_sync import (
    sync_all_game_logs,
    sync_game_center_full_backfill,
    sync_game_center_game_logs,
    sync_player_game_log,
    sync_players,
    sync_schedule_for_dates,
)
from app.services.scan_evaluator import ScanEvaluatorService
from app.services.season import current_season_id
from app.services.week_schedule import update_current_week_schedule
from app.services.yahoo_oauth_service import has_yahoo_credentials
from app.services.yahoo_service import update_player_ownership

router = APIRouter(prefix="/admin", tags=["Admin"])
settings = get_settings()


def require_admin_user(current_user: User = Depends(get_current_user)) -> User:
    # v2 single-owner mode: any authenticated user is treated as admin.
    return current_user


def _set_sync_state(db: Session, key: str, when: datetime | None = None) -> None:
    now = when or datetime.now(timezone.utc)
    state = db.query(SyncState).filter(SyncState.key == key).first()
    if state:
        state.last_run_at = now
    else:
        db.add(SyncState(key=key, last_run_at=now))
    db.commit()


def _refresh_scan_counts(db: Session, stale_minutes: int = 30, force: bool = False) -> int:
    scans = db.query(Scan).all()
    if not scans:
        return 0
    return ScanEvaluatorService.refresh_match_counts(
        db,
        scans,
        stale_minutes=stale_minutes,
        force=force,
    )


@router.get("")
def admin_root(_: User = Depends(require_admin_user)):
    return {
        "name": "Forecheck v2 Admin",
        "status_endpoint": "/admin/status",
        "sync_endpoints": [
            "/admin/sync/players",
            "/admin/sync/game-logs",
            "/admin/sync/game-logs/full",
            "/admin/sync/rolling-stats",
            "/admin/sync/weekly-schedule",
            "/admin/sync/ownership",
            "/admin/sync/pipeline",
        ],
    }


@router.get("/status")
def admin_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_user),
):
    states = db.query(SyncState).all()
    state_map = {state.key: state.last_run_at for state in states}
    checkpoint = db.query(SyncCheckpoint).filter(SyncCheckpoint.job == "nhl_game_logs").first()

    yahoo_user = (
        db.query(User)
        .filter(
            User.yahoo_access_token.isnot(None),
            User.yahoo_refresh_token.isnot(None),
        )
        .first()
    )
    game_log_summary = db.query(
        func.count(PlayerGameStats.id),
        func.min(PlayerGameStats.date),
        func.max(PlayerGameStats.date),
    ).one()
    recent_runs = db.query(SyncRun).order_by(SyncRun.started_at.desc()).limit(10).all()
    running_jobs = [run.job for run in recent_runs if run.status == "running"]

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
        "last_scan_counts_at": state_map.get("scan_counts"),
        "last_weekly_schedule_at": state_map.get("weekly_schedule"),
        "last_ownership_sync_at": state_map.get("yahoo_ownership"),
        "game_log_checkpoint_date": checkpoint.last_game_date if checkpoint else None,
        "game_log_row_count": int(game_log_summary[0] or 0),
        "game_log_min_date": game_log_summary[1],
        "game_log_max_date": game_log_summary[2],
        "running_jobs": running_jobs,
        "recent_runs": [
            {
                "job": run.job,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "row_count": run.row_count,
                "error": run.error,
            }
            for run in recent_runs
        ],
        "yahoo_enabled": settings.yahoo_enabled,
        "yahoo_connected": settings.yahoo_enabled and has_yahoo_credentials(yahoo_user),
        "server_time_utc": datetime.now(timezone.utc),
    }


@router.post("/player/refresh")
def refresh_player_logs(
    player_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_user),
):
    target = db.query(Player).filter(Player.id == player_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    count = sync_player_game_log(db, target, season_id=current_season_id())
    _set_sync_state(db, "nhl_game_logs")
    return {"status": "ok", "updated": count}


@router.post("/sync/players")
def sync_players_endpoint(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    count = sync_players(db)
    _set_sync_state(db, "players")
    return {"status": "ok", "updated": count}


@router.post("/sync/game-logs")
def sync_game_logs_endpoint(
    backfill_days: int | None = Query(default=None, ge=1, le=30),
    delay_seconds: float | None = Query(default=None, ge=0),
    update_rolling: bool = True,
    refresh_scan_counts: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_user),
):
    count = sync_game_center_game_logs(
        db,
        season_id=current_season_id(),
        backfill_days=backfill_days,
        delay_seconds=delay_seconds,
    )
    _set_sync_state(db, "nhl_game_logs")

    rolling_updated = None
    scan_counts_updated = None
    if update_rolling:
        rolling_updated = AnalyticsService.update_all_rolling_stats(db)
        _set_sync_state(db, "rolling_stats")
    if refresh_scan_counts:
        scan_counts_updated = _refresh_scan_counts(db, force=True)
        _set_sync_state(db, "scan_counts")

    return {
        "status": "ok",
        "updated": count,
        "rolling_stats_updated": rolling_updated,
        "scan_counts_updated": scan_counts_updated,
    }


@router.post("/sync/game-logs/full")
def sync_game_logs_full_endpoint(
    reset_existing: bool = Query(default=False),
    delay_seconds: float | None = Query(default=None, ge=0),
    update_rolling: bool = True,
    refresh_scan_counts: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_user),
):
    count = sync_game_center_full_backfill(
        db,
        season_id=current_season_id(),
        delay_seconds=delay_seconds,
        reset_existing=reset_existing,
    )
    _set_sync_state(db, "nhl_game_logs")

    rolling_updated = None
    scan_counts_updated = None
    if update_rolling:
        rolling_updated = AnalyticsService.update_all_rolling_stats(db)
        _set_sync_state(db, "rolling_stats")
    if refresh_scan_counts:
        scan_counts_updated = _refresh_scan_counts(db, force=True)
        _set_sync_state(db, "scan_counts")

    return {
        "status": "ok",
        "updated": count,
        "rolling_stats_updated": rolling_updated,
        "scan_counts_updated": scan_counts_updated,
    }


@router.post("/sync/rolling-stats")
def sync_rolling_stats_endpoint(
    refresh_scan_counts: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_user),
):
    count = AnalyticsService.update_all_rolling_stats(db)
    _set_sync_state(db, "rolling_stats")
    scan_counts_updated = None
    if refresh_scan_counts:
        scan_counts_updated = _refresh_scan_counts(db, force=True)
        _set_sync_state(db, "scan_counts")
    return {"status": "ok", "updated": count, "scan_counts_updated": scan_counts_updated}


@router.post("/sync/weekly-schedule")
def sync_weekly_schedule_endpoint(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    today = datetime.now(timezone.utc).date()
    dates = [datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)]
    for offset in range(0, 14):
        dates.append(datetime.combine(today + timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc))
    schedule_count = sync_schedule_for_dates(db, dates)
    update_current_week_schedule(db)
    _set_sync_state(db, "weekly_schedule")
    return {"status": "ok", "updated": schedule_count}


@router.post("/sync/ownership")
async def sync_ownership_endpoint(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
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
async def sync_pipeline_endpoint(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):

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
    scan_counts_updated = _refresh_scan_counts(db, force=True)
    _set_sync_state(db, "scan_counts")

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
        "scan_counts_updated": scan_counts_updated,
        "yahoo_updated": yahoo_updated,
    }
