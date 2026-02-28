from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.routers.auth import get_current_user, get_current_user_optional
from app.models.user import User as UserModel
from app.models.scan import Scan as ScanModel, ScanRule as ScanRuleModel, ScanPreference
from app.models.player import Player as PlayerModel
from app.schemas.scan import Scan, ScanCreate, ScanUpdate, ScanRule, ScanPreview
from app.schemas.player import Player
from app.services.scan_evaluator import ScanEvaluatorService

router = APIRouter(prefix="/scans", tags=["Scans"])


# Preset scans configuration
PRESET_SCANS = [
    {
        "name": "Banger Stud",
        "description": "Shots, hits, and blocks over the last 20 games",
        "rules": [
            {"stat": "shots", "comparator": ">", "value": 2, "window": "L20"},
            {"stat": "hits", "comparator": ">", "value": 2, "window": "L20"},
            {"stat": "blocks", "comparator": ">", "value": 2, "window": "L20"},
        ]
    },
    {
        "name": "Buy Low Shooters",
        "description": "High shot volume with low shooting percentage",
        "rules": [
            {"stat": "shots", "comparator": ">", "value": 3, "window": "L10"},
            {"stat": "shooting_percentage", "comparator": "<", "value": 0.08, "window": "L10"},
        ]
    },
    {
        "name": "Sell High Shooters",
        "description": "Low shot volume with high shooting percentage",
        "rules": [
            {"stat": "shots", "comparator": "<", "value": 2.5, "window": "L10"},
            {"stat": "shooting_percentage", "comparator": ">", "value": 0.20, "window": "L10"},
        ]
    },
    {
        "name": "Deployment Bump",
        "description": "TOI up 1.5+ minutes over L5 vs Season",
        "rules": [
            {"stat": "time_on_ice_delta", "comparator": ">=", "value": 1.5, "window": "L5", "compare_window": "Season"},
        ]
    },
    {
        "name": "Volume Starters",
        "description": "Goalies starting 4+ of their last 5 games",
        "rules": [
            {"stat": "goalie_starts", "comparator": ">=", "value": 4, "window": "L5"},
        ]
    },
    {
        "name": "High Volume Saves",
        "description": "Goalies averaging 28+ saves over L10",
        "rules": [
            {"stat": "saves_per_game", "comparator": ">", "value": 28, "window": "L10"},
        ]
    },
    {
        "name": "Power Play QB",
        "description": "Defensemen with strong power play production",
        "rules": [
            {"stat": "power_play_points", "comparator": ">=", "value": 0.3, "window": "L10"},
        ]
    },
    {
        "name": "Hot Goalies",
        "description": "Goalies starting 2+ games with elite save percentage",
        "rules": [
            {"stat": "goalie_starts", "comparator": ">=", "value": 2, "window": "L5"},
            {"stat": "save_percentage", "comparator": ">=", "value": 0.920, "window": "L5"},
        ]
    },
    {
        "name": "B2B Spot Start",
        "description": "Goalies with L5 SV% > .910, <50% of L10 starts, and a B2B within the next few days",
        "rules": [
            {"stat": "b2b_start_opportunity", "comparator": ">=", "value": 1, "window": "L5"},
        ]
    },
]


def ensure_preset_scans(db: Session):
    """Ensure preset scans exist in the database."""
    existing_scans = db.query(ScanModel).filter(ScanModel.is_preset == True).all()
    existing_by_name = {scan.name: scan for scan in existing_scans}
    desired_names = {preset["name"] for preset in PRESET_SCANS}

    removed = [scan for scan in existing_scans if scan.name not in desired_names]
    if removed:
        removed_ids = [scan.id for scan in removed]
        db.query(ScanPreference).filter(ScanPreference.scan_id.in_(removed_ids)).delete(synchronize_session=False)
        for scan in removed:
            db.delete(scan)

    for preset in PRESET_SCANS:
        scan = existing_by_name.get(preset["name"])
        if not scan:
            scan = ScanModel(
                name=preset["name"],
                description=preset["description"],
                is_preset=True,
            )
            db.add(scan)
            db.flush()
        else:
            scan.description = preset["description"]
            scan.is_preset = True
            db.query(ScanRuleModel).filter(ScanRuleModel.scan_id == scan.id).delete()

        for rule_data in preset["rules"]:
            rule = ScanRuleModel(
                scan_id=scan.id,
                stat=rule_data["stat"],
                comparator=rule_data["comparator"],
                value=rule_data["value"],
                window=rule_data["window"],
                compare_window=rule_data.get("compare_window"),
            )
            db.add(rule)

    db.commit()


def _apply_scan_preferences(
    scans: List[ScanModel],
    preferences: dict[str, ScanPreference],
    include_hidden: bool,
) -> List[ScanModel]:
    if not scans:
        return scans
    filtered: List[ScanModel] = []
    for scan in scans:
        if not scan.is_preset:
            filtered.append(scan)
            continue
        pref = preferences.get(scan.id)
        is_hidden = pref.is_hidden if pref else False
        if is_hidden and not include_hidden:
            continue
        scan.is_hidden = is_hidden
        if pref is not None:
            scan.is_followed = pref.is_followed
            scan.alerts_enabled = pref.alerts_enabled
        filtered.append(scan)
    return filtered


def _build_scan_query(
    db: Session,
    current_user: UserModel | None,
    include_presets: bool,
):
    query = db.query(ScanModel)
    if current_user:
        if include_presets:
            return query.filter(
                (ScanModel.is_preset == True) |
                (ScanModel.user_id == current_user.id)
            )
        return query.filter(ScanModel.user_id == current_user.id)
    if include_presets:
        return query.filter(ScanModel.is_preset == True)
    return query.filter(ScanModel.id == "__no_scans__")


def _attach_scan_preferences(
    db: Session,
    scans: List[ScanModel],
    current_user: UserModel | None,
    include_hidden: bool,
) -> List[ScanModel]:
    if not current_user:
        return scans
    preset_ids = [scan.id for scan in scans if scan.is_preset]
    if not preset_ids:
        return scans
    prefs = db.query(ScanPreference).filter(
        ScanPreference.user_id == current_user.id,
        ScanPreference.scan_id.in_(preset_ids),
    ).all()
    pref_map = {pref.scan_id: pref for pref in prefs}
    return _apply_scan_preferences(scans, pref_map, include_hidden)


def _refresh_scan_match_counts(
    db: Session,
    scans: List[ScanModel],
    stale_minutes: int = 30,
    force: bool = False,
) -> None:
    ScanEvaluatorService.refresh_match_counts(
        db,
        scans,
        stale_minutes=stale_minutes,
        force=force,
    )


@router.get("", response_model=List[Scan])
async def get_scans(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user_optional),
    include_presets: bool = True,
    include_hidden: bool = False,
    refresh_counts: bool = False,
    stale_minutes: int = Query(30, ge=1, le=1440),
    force_refresh: bool = False,
):
    """Get all scans (presets and user's custom scans)."""
    ensure_preset_scans(db)
    scans = _build_scan_query(db, current_user, include_presets).all()
    scans = _attach_scan_preferences(db, scans, current_user, include_hidden)
    if refresh_counts:
        _refresh_scan_match_counts(
            db,
            scans,
            stale_minutes=stale_minutes,
            force=force_refresh,
        )
    return scans


@router.get("/presets", response_model=List[Scan])
async def get_preset_scans(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user_optional),
    include_hidden: bool = False,
    refresh_counts: bool = False,
    stale_minutes: int = Query(30, ge=1, le=1440),
    force_refresh: bool = False,
):
    """Get all preset scans."""
    ensure_preset_scans(db)
    scans = db.query(ScanModel).filter(ScanModel.is_preset == True).all()
    scans = _attach_scan_preferences(db, scans, current_user, include_hidden)
    if refresh_counts:
        _refresh_scan_match_counts(
            db,
            scans,
            stale_minutes=stale_minutes,
            force=force_refresh,
        )
    return scans


@router.post("", response_model=Scan)
async def create_scan(
    scan_data: ScanCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Create a new custom scan."""
    scan = ScanModel(
        user_id=current_user.id,
        name=scan_data.name,
        description=scan_data.description,
        position_filter=scan_data.position_filter,
        is_preset=False,
        alerts_enabled=scan_data.alerts_enabled,
    )
    db.add(scan)
    db.flush()

    # Add rules
    for rule_data in scan_data.rules:
        rule = ScanRuleModel(
            scan_id=scan.id,
            stat=rule_data.stat,
            comparator=rule_data.comparator,
            value=rule_data.value,
            window=rule_data.window,
            compare_window=rule_data.compare_window,
        )
        db.add(rule)

    db.commit()
    db.refresh(scan)

    # Update user's scan count
    current_user.scans_created += 1
    db.commit()

    return scan


@router.post("/refresh-counts", response_model=List[Scan])
async def refresh_scan_counts(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
    include_presets: bool = True,
    include_hidden: bool = True,
    stale_minutes: int = Query(30, ge=1, le=1440),
    force: bool = False,
):
    """Refresh match counts and last_evaluated timestamps for visible scans."""
    ensure_preset_scans(db)
    scans = _build_scan_query(db, current_user, include_presets).all()
    scans = _attach_scan_preferences(db, scans, current_user, include_hidden)
    _refresh_scan_match_counts(db, scans, stale_minutes=stale_minutes, force=force)
    return scans


@router.get("/{scan_id}", response_model=Scan)
async def get_scan(
    scan_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific scan."""
    scan = db.query(ScanModel).filter(ScanModel.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.put("/{scan_id}", response_model=Scan)
async def update_scan(
    scan_id: str,
    scan_data: ScanUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Update a scan."""
    scan = db.query(ScanModel).filter(ScanModel.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.is_preset:
        pref = db.query(ScanPreference).filter(
            ScanPreference.user_id == current_user.id,
            ScanPreference.scan_id == scan.id,
        ).first()
        if not pref:
            pref = ScanPreference(
                user_id=current_user.id,
                scan_id=scan.id,
            )
            db.add(pref)
            db.flush()

        if scan_data.is_followed is not None:
            pref.is_followed = scan_data.is_followed
        if scan_data.is_hidden is not None:
            pref.is_hidden = scan_data.is_hidden
        if scan_data.alerts_enabled is not None:
            pref.alerts_enabled = scan_data.alerts_enabled

        scan.is_followed = pref.is_followed
        scan.alerts_enabled = pref.alerts_enabled
        scan.is_hidden = pref.is_hidden
    else:
        if scan.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this scan")

        if scan_data.name is not None:
            scan.name = scan_data.name
        if scan_data.description is not None:
            scan.description = scan_data.description
        if "position_filter" in scan_data.model_fields_set:
            scan.position_filter = scan_data.position_filter
        if scan_data.is_followed is not None:
            scan.is_followed = scan_data.is_followed
        if scan_data.alerts_enabled is not None:
            scan.alerts_enabled = scan_data.alerts_enabled

        if scan_data.rules is not None:
            # Delete existing rules and add new ones
            db.query(ScanRuleModel).filter(ScanRuleModel.scan_id == scan.id).delete()
            for rule_data in scan_data.rules:
                rule = ScanRuleModel(
                    scan_id=scan.id,
                    stat=rule_data.stat,
                    comparator=rule_data.comparator,
                    value=rule_data.value,
                    window=rule_data.window,
                    compare_window=rule_data.compare_window,
                )
                db.add(rule)

    db.commit()
    db.refresh(scan)
    return scan


@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Delete a custom scan."""
    scan = db.query(ScanModel).filter(ScanModel.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.is_preset:
        raise HTTPException(status_code=403, detail="Cannot delete preset scans")

    if scan.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this scan")

    db.delete(scan)
    db.commit()

    return {"message": "Scan deleted"}


@router.post("/{scan_id}/evaluate", response_model=List[Player])
async def evaluate_scan(
    scan_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(50, le=100),
):
    """Evaluate a scan and return matching players."""
    scan = db.query(ScanModel).filter(ScanModel.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    results = ScanEvaluatorService.evaluate(db, scan)

    # Update scan metadata
    scan.last_evaluated = datetime.utcnow()
    scan.match_count = len(results)
    db.commit()

    return results[:limit]


@router.post("/preview", response_model=List[Player])
async def preview_scan(
    scan_data: ScanPreview,
    db: Session = Depends(get_db),
    limit: int = Query(10, le=50),
):
    """Preview a scan without saving it."""
    scan = ScanModel(
        id=str(uuid.uuid4()),
        name=scan_data.name or "Preview",
        description=scan_data.description or "",
        position_filter=scan_data.position_filter,
        is_preset=False,
        alerts_enabled=False,
    )
    scan.rules = [
        ScanRuleModel(
            scan_id=scan.id,
            stat=rule.stat,
            comparator=rule.comparator,
            value=rule.value,
            window=rule.window,
            compare_window=rule.compare_window,
        )
        for rule in scan_data.rules
    ]
    results = ScanEvaluatorService.preview_results(db, scan, limit=limit)
    return results
