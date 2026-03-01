from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User as UserModel
from app.models.league import League as LeagueModel
from app.schemas.league import League, LeagueCreate, LeagueUpdate

router = APIRouter(prefix="/leagues", tags=["Leagues"])


# Default scoring weights
DEFAULT_CATEGORIES_WEIGHTS = {
    "goals": 1,
    "assists": 1,
    "points": 1,
    "plus_minus": 1,
    "pim": 1,
    "power_play_points": 1,
    "shots": 1,
    "hits": 1,
    "blocks": 1,
    "wins": 1,
    "save_percentage": 1,
    "goals_against_average": 1,
    "saves": 1,
    "shutouts": 1,
}

DEFAULT_POINTS_WEIGHTS = {
    "goals": 3,
    "assists": 2,
    "plus_minus": 0.5,
    "pim": 0.0,
    "power_play_points": 1,
    "shorthanded_points": 2,
    "shots": 0.4,
    "hits": 0.2,
    "blocks": 0.2,
    "wins": 3,
    "saves": 0.2,
    "goals_against": -1,
    "shutouts": 5,
}


def _default_weights_for(league_type: str) -> dict[str, float]:
    return dict(DEFAULT_CATEGORIES_WEIGHTS if league_type == "categories" else DEFAULT_POINTS_WEIGHTS)


def _deactivate_other_leagues(db: Session, user_id: str, active_league_id: str) -> None:
    db.query(LeagueModel).filter(
        LeagueModel.user_id == user_id,
        LeagueModel.id != active_league_id,
        LeagueModel.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)


def _ensure_one_active_league(db: Session, user_id: str) -> None:
    active_count = db.query(LeagueModel).filter(
        LeagueModel.user_id == user_id,
        LeagueModel.is_active == True,
    ).count()
    if active_count > 0:
        return
    fallback = db.query(LeagueModel).filter(
        LeagueModel.user_id == user_id
    ).order_by(LeagueModel.updated_at.desc(), LeagueModel.created_at.desc()).first()
    if fallback:
        fallback.is_active = True


@router.get("", response_model=List[League])
async def get_leagues(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Get user's leagues."""
    leagues = db.query(LeagueModel).filter(
        LeagueModel.user_id == current_user.id
    ).all()
    return leagues


@router.post("", response_model=League)
async def create_league(
    league_data: LeagueCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Create a new league."""
    league_type = (
        league_data.league_type.value
        if hasattr(league_data.league_type, "value")
        else str(league_data.league_type)
    )
    has_existing = db.query(LeagueModel.id).filter(LeagueModel.user_id == current_user.id).first() is not None
    is_active = league_data.is_active if league_data.is_active is not None else not has_existing

    # Set default weights if not provided.
    scoring_weights = dict(league_data.scoring_weights or _default_weights_for(league_type))

    league = LeagueModel(
        user_id=current_user.id,
        name=league_data.name,
        league_type=league_type,
        scoring_weights=scoring_weights,
        is_active=is_active,
    )
    db.add(league)
    db.flush()

    if league.is_active:
        _deactivate_other_leagues(db, current_user.id, league.id)

    db.commit()
    db.refresh(league)

    return league


@router.get("/{league_id}", response_model=League)
async def get_league(
    league_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Get a specific league."""
    league = db.query(LeagueModel).filter(LeagueModel.id == league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this league")

    return league


@router.put("/{league_id}", response_model=League)
async def update_league(
    league_id: str,
    league_data: LeagueUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Update a league."""
    league = db.query(LeagueModel).filter(LeagueModel.id == league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this league")

    if league_data.name is not None:
        league.name = league_data.name

    if league_data.league_type is not None:
        league.league_type = (
            league_data.league_type.value
            if hasattr(league_data.league_type, "value")
            else str(league_data.league_type)
        )
        if league_data.scoring_weights is None:
            league.scoring_weights = _default_weights_for(league.league_type)

    if league_data.scoring_weights is not None:
        league.scoring_weights = dict(league_data.scoring_weights)

    if league_data.is_active is not None:
        league.is_active = league_data.is_active

    if league.is_active:
        _deactivate_other_leagues(db, current_user.id, league.id)
    else:
        _ensure_one_active_league(db, current_user.id)

    db.commit()
    db.refresh(league)

    return league


@router.delete("/{league_id}")
async def delete_league(
    league_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Delete a league."""
    league = db.query(LeagueModel).filter(LeagueModel.id == league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this league")

    was_active = bool(league.is_active)
    db.delete(league)
    db.commit()

    if was_active:
        replacement = db.query(LeagueModel).filter(
            LeagueModel.user_id == current_user.id
        ).order_by(LeagueModel.updated_at.desc(), LeagueModel.created_at.desc()).first()
        if replacement:
            replacement.is_active = True
            db.commit()

    return {"message": "League deleted"}
