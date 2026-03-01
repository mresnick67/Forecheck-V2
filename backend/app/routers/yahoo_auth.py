"""Yahoo Fantasy API OAuth endpoints."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.yahoo_oauth_service import (
    exchange_code_for_tokens,
    refresh_access_token,
    write_oauth_file,
)

router = APIRouter(prefix="/auth/yahoo", tags=["Yahoo OAuth"])
settings = get_settings()
logger = logging.getLogger(__name__)

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
_oauth_states: dict[str, str] = {}


class YahooConnectionStatus(BaseModel):
    connected: bool
    yahoo_user_guid: Optional[str] = None
    expires_at: Optional[datetime] = None


def _ensure_enabled() -> None:
    if not settings.yahoo_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yahoo integration is disabled. Set YAHOO_ENABLED=true to enable it.",
        )


@router.get("/login")
async def yahoo_login(
    current_user: User = Depends(get_current_user),
    redirect: bool = Query(True, description="Redirect to Yahoo auth URL"),
):
    _ensure_enabled()
    if not settings.yahoo_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yahoo API not configured (missing YAHOO_CLIENT_ID)",
        )

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = current_user.id

    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.resolved_yahoo_redirect_uri,
        "response_type": "code",
        "scope": "openid fspt-r",
        "state": state,
    }
    auth_url = f"{YAHOO_AUTH_URL}?{urlencode(params)}"

    if redirect:
        return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    return {"authorization_url": auth_url}


@router.get("/callback")
async def yahoo_callback(
    code: str = Query(..., description="Authorization code from Yahoo"),
    state: str = Query(..., description="State token for CSRF protection"),
    db: Session = Depends(get_db),
):
    _ensure_enabled()

    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        tokens = await exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("Failed to exchange Yahoo auth code: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to authenticate with Yahoo: {exc}",
        )

    user.yahoo_access_token = tokens.access_token
    user.yahoo_refresh_token = tokens.refresh_token
    user.yahoo_token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.expires_in)
    user.yahoo_user_guid = tokens.xoauth_yahoo_guid
    db.commit()

    try:
        write_oauth_file(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            token_type=tokens.token_type,
            yahoo_guid=tokens.xoauth_yahoo_guid,
        )
    except Exception as exc:
        logger.warning("Failed to write Yahoo OAuth file: %s", exc)

    return HTMLResponse(
        content="""
        <!doctype html>
        <html>
          <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <title>Yahoo Connected</title>
            <style>
              body { font-family: Arial, sans-serif; background: #0b0f14; color: #eef3f8; padding: 32px; }
              .card { max-width: 520px; margin: 0 auto; background: #111826; padding: 24px; border-radius: 14px; }
            </style>
          </head>
          <body>
            <div class=\"card\">
              <h1>Yahoo Connected</h1>
              <p>Connection complete. Returning to the app...</p>
            </div>
            <script>
              try {
                if (window.opener) {
                  window.opener.postMessage({ type: "forecheck-yahoo-connected" }, "*");
                  window.close();
                }
                setTimeout(function () {
                  window.location.href = "/";
                }, 1200);
              } catch (e) {
                window.location.href = "/";
              }
            </script>
          </body>
        </html>
        """,
        status_code=status.HTTP_200_OK,
    )


@router.get("/status", response_model=YahooConnectionStatus)
async def yahoo_status(current_user: User = Depends(get_current_user)):
    _ensure_enabled()
    connected = bool(current_user.yahoo_access_token and current_user.yahoo_refresh_token)
    return YahooConnectionStatus(
        connected=connected,
        yahoo_user_guid=current_user.yahoo_user_guid if connected else None,
        expires_at=current_user.yahoo_token_expires_at if connected else None,
    )


@router.post("/disconnect")
async def yahoo_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_enabled()
    current_user.yahoo_access_token = None
    current_user.yahoo_refresh_token = None
    current_user.yahoo_token_expires_at = None
    current_user.yahoo_user_guid = None
    db.commit()
    return {"message": "Yahoo account disconnected"}


@router.post("/refresh")
async def yahoo_refresh(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_enabled()
    if not current_user.yahoo_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Yahoo account connected",
        )

    try:
        tokens = await refresh_access_token(current_user.yahoo_refresh_token)
    except Exception as exc:
        logger.error("Failed to refresh Yahoo token: %s", exc)
        current_user.yahoo_access_token = None
        current_user.yahoo_refresh_token = None
        current_user.yahoo_token_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refresh Yahoo token. Please reconnect.",
        )

    current_user.yahoo_access_token = tokens.access_token
    current_user.yahoo_refresh_token = tokens.refresh_token
    current_user.yahoo_token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.expires_in)
    db.commit()

    try:
        write_oauth_file(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            token_type=tokens.token_type,
            yahoo_guid=tokens.xoauth_yahoo_guid,
        )
    except Exception as exc:
        logger.warning("Failed to write Yahoo OAuth file: %s", exc)

    return {"message": "Token refreshed", "expires_at": current_user.yahoo_token_expires_at}
