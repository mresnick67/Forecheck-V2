from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import get_settings
from app.models.user import User
from app.schemas.user import UserCreate, TokenData

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    @staticmethod
    def _hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt

    @staticmethod
    def issue_refresh_token(db: Session, user: User) -> str:
        refresh_token = secrets.token_urlsafe(48)
        user.refresh_token_hash = AuthService._hash_refresh_token(refresh_token)
        user.refresh_token_expires_at = datetime.utcnow() + timedelta(
            days=settings.refresh_token_expire_days
        )
        user.refresh_token_last_used_at = datetime.utcnow()
        db.add(user)
        db.commit()
        return refresh_token

    @staticmethod
    def rotate_refresh_token(db: Session, user: User) -> str:
        refresh_token = secrets.token_urlsafe(48)
        user.refresh_token_hash = AuthService._hash_refresh_token(refresh_token)
        user.refresh_token_expires_at = datetime.utcnow() + timedelta(
            days=settings.refresh_token_expire_days
        )
        user.refresh_token_last_used_at = datetime.utcnow()
        db.add(user)
        db.commit()
        return refresh_token

    @staticmethod
    def clear_refresh_token(db: Session, user: User) -> None:
        user.refresh_token_hash = None
        user.refresh_token_expires_at = None
        user.refresh_token_last_used_at = None
        db.add(user)
        db.commit()

    @staticmethod
    def decode_token(token: str) -> Optional[TokenData]:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return TokenData(user_id=user_id)
        except JWTError:
            return None

    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        # Check if username exists
        if db.query(User).filter(User.username == user_data.username).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
        # Check if email exists
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        hashed_password = AuthService.get_password_hash(user_data.password)
        display_name = user_data.display_name or user_data.username
        db_user = User(
            username=user_data.username,
            email=user_data.email,
            display_name=display_name,
            hashed_password=hashed_password,
            bio=user_data.bio or "",
            avatar_url=user_data.avatar_url,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_refresh_token(db: Session, refresh_token: str) -> Optional[User]:
        if not refresh_token:
            return None
        token_hash = AuthService._hash_refresh_token(refresh_token)
        return db.query(User).filter(User.refresh_token_hash == token_hash).first()
