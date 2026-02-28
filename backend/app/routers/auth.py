from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_db
from app.config import get_settings
from app.services.auth import AuthService
from app.schemas.user import User, UserCreate, Token, TokenRefreshRequest
from app.models.user import User as UserModel

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[UserModel]:
    if not token:
        return None
    token_data = AuthService.decode_token(token)
    if not token_data:
        return None
    user = AuthService.get_user_by_id(db, token_data.user_id)
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserModel:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = AuthService.decode_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = AuthService.get_user_by_id(db, token_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", response_model=User)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    if not settings.enable_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled in this deployment",
        )
    user = AuthService.create_user(db, user_data)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and get access token."""
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = AuthService.create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    refresh_token = AuthService.issue_refresh_token(db, user)
    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=int(access_token_expires.total_seconds()),
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: TokenRefreshRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using a refresh token."""
    user = AuthService.get_user_by_refresh_token(db, payload.refresh_token)
    if not user or not user.refresh_token_expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.refresh_token_expires_at < datetime.utcnow():
        AuthService.clear_refresh_token(db, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = AuthService.create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    refresh_token = AuthService.rotate_refresh_token(db, user)
    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=int(access_token_expires.total_seconds()),
    )


@router.get("/me", response_model=User)
async def get_me(current_user: UserModel = Depends(get_current_user)):
    """Get current user info."""
    return current_user
