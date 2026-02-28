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
}

DEFAULT_POINTS_WEIGHTS = {
    "goals": 3,
    "assists": 2,
    "plus_minus": 1,
    "pim": 0.5,
    "power_play_points": 1,
    "shorthanded_points": 2,
    "shots": 0.4,
    "hits": 0.5,
    "blocks": 0.5,
}


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
    # Set default weights if not provided
    scoring_weights = league_data.scoring_weights
    if not scoring_weights:
        if league_data.league_type == "categories":
            scoring_weights = DEFAULT_CATEGORIES_WEIGHTS
        else:
            scoring_weights = DEFAULT_POINTS_WEIGHTS

    league = LeagueModel(
        user_id=current_user.id,
        name=league_data.name,
        league_type=league_data.league_type,
        scoring_weights=scoring_weights,
    )
    db.add(league)
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
        league.league_type = league_data.league_type
    if league_data.scoring_weights is not None:
        league.scoring_weights = league_data.scoring_weights
    if league_data.is_active is not None:
        league.is_active = league_data.is_active

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

    db.delete(league)
    db.commit()

    return {"message": "League deleted"}
