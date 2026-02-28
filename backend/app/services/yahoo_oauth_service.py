from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User

try:
    from yahoo_oauth import OAuth2
except Exception:  # pragma: no cover - optional import for environments without yahoo_oauth
    OAuth2 = None

logger = logging.getLogger(__name__)
settings = get_settings()

YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
DEFAULT_EXPIRES_IN = 3600


class YahooTokenResponse(BaseModel):
    """Response from Yahoo token endpoint."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    xoauth_yahoo_guid: Optional[str] = None


def _resolve_oauth_path() -> Path:
    path = Path(settings.yahoo_oauth_path).expanduser()
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def oauth_file_exists() -> bool:
    return _resolve_oauth_path().exists()


def get_oauth_file_status() -> tuple[bool, Optional[datetime]]:
    path = _resolve_oauth_path()
    if not path.exists():
        return False, None
    refreshed_at = None
    try:
        payload = json.loads(path.read_text())
        token_time = payload.get("token_time")
        if token_time:
            refreshed_at = datetime.fromtimestamp(int(token_time), tz=timezone.utc)
    except Exception as exc:
        logger.warning("Failed to read Yahoo OAuth file timestamp: %s", exc)
    if not refreshed_at:
        try:
            refreshed_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception as exc:
            logger.warning("Failed to read Yahoo OAuth file mtime: %s", exc)
    return True, refreshed_at


def write_oauth_file(
    access_token: str,
    refresh_token: str,
    expires_in: Optional[int],
    token_type: Optional[str] = None,
    yahoo_guid: Optional[str] = None,
) -> Optional[Path]:
    if not settings.yahoo_client_id or not settings.yahoo_client_secret:
        logger.warning("Yahoo OAuth file not written: missing client ID/secret")
        return None
    if not access_token or not refresh_token:
        logger.warning("Yahoo OAuth file not written: missing token values")
        return None

    payload = {
        "consumer_key": settings.yahoo_client_id,
        "consumer_secret": settings.yahoo_client_secret,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": token_type or "bearer",
        "expires_in": int(expires_in or DEFAULT_EXPIRES_IN),
        "token_time": int(time.time()),
    }
    if yahoo_guid:
        payload["xoauth_yahoo_guid"] = yahoo_guid

    path = _resolve_oauth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path


def _persist_oauth_token(oauth: OAuth2) -> None:
    token = getattr(oauth, "token", None) or {}
    access_token = token.get("access_token") or getattr(oauth, "access_token", None)
    refresh_token = token.get("refresh_token") or getattr(oauth, "refresh_token", None)
    expires_in = token.get("expires_in") or DEFAULT_EXPIRES_IN
    token_type = token.get("token_type") or "bearer"
    yahoo_guid = token.get("xoauth_yahoo_guid")

    if access_token and refresh_token:
        write_oauth_file(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
            yahoo_guid=yahoo_guid,
        )


def _get_oauth_client() -> Optional[OAuth2]:
    if OAuth2 is None:
        logger.warning("yahoo_oauth not installed; cannot use oauth2.json")
        return None
    oauth_path = _resolve_oauth_path()
    if not oauth_path.exists():
        return None
    try:
        return OAuth2(None, None, from_file=str(oauth_path))
    except Exception as exc:
        logger.error("Failed to load Yahoo OAuth file: %s", exc)
        return None


def get_access_token_from_file() -> Optional[str]:
    oauth = _get_oauth_client()
    if not oauth:
        return None

    try:
        if not oauth.token_is_valid():
            logger.info("Yahoo OAuth token expired; refreshing")
            oauth.refresh_access_token()
            _persist_oauth_token(oauth)
    except Exception as exc:
        logger.error("Failed to refresh Yahoo OAuth token: %s", exc)
        return None

    token = getattr(oauth, "token", None) or {}
    access_token = token.get("access_token") or getattr(oauth, "access_token", None)
    if not access_token:
        logger.error("Yahoo OAuth token missing access_token")
        return None
    return access_token


def _expires_in_from_user(user: User) -> Optional[int]:
    if not user.yahoo_token_expires_at:
        return None
    remaining = user.yahoo_token_expires_at - datetime.utcnow()
    seconds = int(remaining.total_seconds())
    return max(seconds, 0)


def has_yahoo_credentials(user: Optional[User] = None) -> bool:
    if oauth_file_exists():
        return True
    if user and user.yahoo_access_token and user.yahoo_refresh_token:
        return True
    return False


async def exchange_code_for_tokens(code: str) -> YahooTokenResponse:
    """Exchange authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            YAHOO_TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error("Yahoo token exchange failed: %s", response.text)
            raise Exception(f"Token exchange failed: {response.text}")

        data = response.json()
        return YahooTokenResponse(**data)


async def refresh_access_token(refresh_token: str) -> YahooTokenResponse:
    """Refresh access token using refresh token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            YAHOO_TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error("Yahoo token refresh failed: %s", response.text)
            raise Exception(f"Token refresh failed: {response.text}")

        data = response.json()
        return YahooTokenResponse(**data)


async def get_valid_yahoo_token(user: User, db: Session) -> Optional[str]:
    """
    Get a valid Yahoo access token for the user.
    Refreshes if expired.
    """
    if not user.yahoo_access_token:
        return None

    if user.yahoo_token_expires_at and user.yahoo_token_expires_at < datetime.utcnow() + timedelta(minutes=5):
        if user.yahoo_refresh_token:
            try:
                tokens = await refresh_access_token(user.yahoo_refresh_token)
                user.yahoo_access_token = tokens.access_token
                user.yahoo_refresh_token = tokens.refresh_token
                user.yahoo_token_expires_at = datetime.utcnow() + timedelta(
                    seconds=tokens.expires_in
                )
                db.commit()
            except Exception as exc:
                logger.error("Failed to refresh token: %s", exc)
                return None
        else:
            return None

    return user.yahoo_access_token


async def get_yahoo_access_token(
    db: Session,
    user: Optional[User] = None,
) -> Optional[str]:
    access_token = get_access_token_from_file()
    if access_token:
        return access_token

    if not user:
        return None

    access_token = await get_valid_yahoo_token(user, db)
    if not access_token or not user.yahoo_refresh_token:
        return access_token

    write_oauth_file(
        access_token=access_token,
        refresh_token=user.yahoo_refresh_token,
        expires_in=_expires_in_from_user(user),
        token_type="bearer",
        yahoo_guid=user.yahoo_user_guid,
    )
    return access_token
