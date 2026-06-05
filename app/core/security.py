from typing import Optional
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException, status

from app.core.config import settings

_serializer = URLSafeTimedSerializer(settings.app_secret_key)

SESSION_COOKIE = "snp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def create_session_token(user_id: str) -> str:
    """Create a signed session token containing the user_id."""
    return _serializer.dumps(user_id, salt="session")


def decode_session_token(token: str, max_age: int = SESSION_MAX_AGE) -> str:
    """Decode and verify session token. Returns user_id."""
    try:
        return _serializer.loads(token, salt="session", max_age=max_age)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please login again.",
        )


def get_session_token(request: Request) -> Optional[str]:
    """Extract raw session token from cookie."""
    return request.cookies.get(SESSION_COOKIE)


async def get_current_user_id(request: Request) -> str:
    """Dependency: extract and validate current user from session cookie."""
    token = get_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return decode_session_token(token)
