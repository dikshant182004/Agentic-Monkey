"""Authentication dependencies for FastAPI routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.config import settings

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Authenticated user context attached to request scope."""

    sub: str
    name: str
    user_id: str


def create_jwt(email: str, name: str, user_id: str) -> str:
    """Create signed JWT token used by Streamlit and API calls."""
    payload = {
        "sub": email,
        "name": name,
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """Resolve current user either from dev bypass or JWT auth header."""
    if settings.dev_bypass_auth:
        return CurrentUser(sub="dev@chaosagent.local", name="Dev User", user_id="00000000-0000-0000-0000-000000000001")

    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        return CurrentUser(sub=payload["sub"], name=payload.get("name", ""), user_id=payload["user_id"])
    except (JWTError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc

