from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User as UserModel
from app.schemas.user import User, UserCreate
from app.services.auth import AuthService

router = APIRouter(prefix="/setup", tags=["Setup"])
settings = get_settings()


class SetupStatusResponse(BaseModel):
    setup_required: bool
    user_count: int
    app_mode: str
    enable_registration: bool
    yahoo_enabled: bool


class SetupBootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = Field(default=None, max_length=100)
    setup_token: str | None = None


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: Session = Depends(get_db)):
    user_count = db.query(UserModel).count()
    return SetupStatusResponse(
        setup_required=user_count == 0,
        user_count=user_count,
        app_mode=settings.app_mode,
        enable_registration=settings.enable_registration,
        yahoo_enabled=settings.yahoo_enabled,
    )


@router.post("/bootstrap", response_model=User, status_code=status.HTTP_201_CREATED)
async def bootstrap_owner(
    payload: SetupBootstrapRequest,
    db: Session = Depends(get_db),
    x_setup_token: str | None = Header(default=None, alias="X-Setup-Token"),
):
    existing_users = db.query(UserModel).count()
    if existing_users > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup already completed. Owner user already exists.",
        )

    required_token = settings.setup_bootstrap_token
    if required_token:
        provided = payload.setup_token or x_setup_token
        if provided != required_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid setup token",
            )

    created = AuthService.create_user(
        db,
        UserCreate(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name or payload.username,
        ),
    )
    return created
