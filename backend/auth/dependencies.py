"""Authentication dependencies for FastAPI routes.

This backend trusts Streamlit to handle the Google OIDC login flow. Streamlit
exposes the user's Google ID token (when configured with expose_tokens="id")
and sends it to the backend as a Bearer token.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.crud import get_or_create_user
from backend.db.session import get_db

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Authenticated user context attached to request scope."""

    sub: str
    name: str
    user_id: str


@lru_cache(maxsize=1)
def _google_openid_config_url() -> str:
    return "https://accounts.google.com/.well-known/openid-configuration"


async def _fetch_google_jwks() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        meta = await client.get(_google_openid_config_url())
        meta.raise_for_status()
        jwks_uri = meta.json()["jwks_uri"]
        jwks = await client.get(jwks_uri)
        jwks.raise_for_status()
        return jwks.json()


async def _verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Verify Google OIDC ID token signature, issuer, and audience."""
    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc

    jwks = await _fetch_google_jwks()
    keys = jwks.get("keys", [])
    key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token key id")

    public_key = jwk.construct(key)
    message, encoded_sig = id_token.rsplit(".", 1)
    decoded_sig = base64url_decode(encoded_sig.encode("utf-8"))
    if not public_key.verify(message.encode("utf-8"), decoded_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        claims = jwt.get_unverified_claims(id_token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims") from exc

    iss = claims.get("iss")
    aud = claims.get("aud")
    if iss not in {"https://accounts.google.com", "accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")
    if settings.google_client_id and aud != settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token audience")
    return claims


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve current user either from dev bypass or Streamlit Google ID token."""
    if settings.dev_bypass_auth:
        user = await get_or_create_user(db, email="dev@chaosagent.local", name="Dev User")
        return CurrentUser(sub=user.email, name=user.name, user_id=str(user.id))

    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")

    claims = await _verify_google_id_token(creds.credentials)
    email = claims.get("email")
    name = claims.get("name") or claims.get("given_name") or ""
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing email claim")

    user = await get_or_create_user(db, email=email, name=name or email)
    return CurrentUser(sub=email, name=user.name, user_id=str(user.id))

