"""Google OAuth routes for ChaosAgent login flow."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import create_jwt
from backend.config import settings
from backend.db.crud import get_or_create_user
from backend.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google")
async def auth_google() -> RedirectResponse:
    """Redirect users to Google OAuth consent endpoint."""
    params = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "consent",
        }
    )
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def auth_google_callback(code: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Handle OAuth callback and redirect to Streamlit with JWT token."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth authorization code")
    if settings.dev_bypass_auth:
        user = await get_or_create_user(db, email="dev@chaosagent.local", name="Dev User")
        token = create_jwt(email=user.email, name=user.name, user_id=str(user.id))
        return RedirectResponse(url=f"{settings.streamlit_url}/?token={token}")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token", "")
            if not access_token:
                raise HTTPException(status_code=400, detail="Google token exchange failed")
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            profile = user_resp.json()
    except httpx.HTTPError as exc:
        logger.exception("Google OAuth callback failed")
        raise HTTPException(status_code=502, detail=f"OAuth provider request failed: {exc}") from exc

    user = await get_or_create_user(db, email=profile["email"], name=profile.get("name", profile["email"]))
    token = create_jwt(email=user.email, name=user.name, user_id=str(user.id))
    return RedirectResponse(url=f"{settings.streamlit_url}/?token={token}")

