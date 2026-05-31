"""Google OAuth routes — legacy / unused.

NOTE: ChaosAgent v2 uses Streamlit's native OIDC flow (st.login / st.user)
combined with Google ID token verification in backend/auth/dependencies.py.
This FastAPI router is NOT registered in main.py and exists only for reference.

BUG-16 fix: the original file imported `create_jwt` from auth.dependencies
but that function does not exist there, causing an ImportError if the module
was ever loaded. The import is removed; if a standalone JWT flow is needed
in future, implement create_jwt in dependencies.py first.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.crud import get_or_create_user
from backend.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google")
async def auth_google() -> RedirectResponse:
    """Redirect users to Google OAuth consent endpoint."""
    redirect_uri = getattr(settings, "google_redirect_uri", "http://localhost:8501/oauth2callback")
    params = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "consent",
        }
    )
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def auth_google_callback(code: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Handle OAuth callback.

    This route is not registered in main.py — it exists for reference only.
    The active auth path is Streamlit OIDC → Google ID token → dependencies.py.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth authorization code")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": getattr(settings, "google_redirect_uri", ""),
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

    await get_or_create_user(db, email=profile["email"], name=profile.get("name", profile["email"]))
    # Redirect to Streamlit — token issuance not implemented here (use Streamlit OIDC)
    return RedirectResponse(url=settings.streamlit_url)