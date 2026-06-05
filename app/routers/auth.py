"""
Auth router — Google OAuth login flow.
Routes:
    GET /auth/login      → redirect to Google consent screen
    GET /auth/callback   → handle Google redirect, create session
    GET /auth/logout     → clear session cookie
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from app.core.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_session_token,
    get_current_user_id,
)
from app.models.user import User
from app.services.google_service import (
    exchange_login_code,
    get_login_authorization_url,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory state store (use Redis in production)
_oauth_states: dict[str, str] = {}


@router.get("/login")
async def login():
    """Redirect user to Google OAuth consent screen."""
    auth_url, state = get_login_authorization_url()
    _oauth_states[state] = "login"
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def auth_callback(request: Request, code: str, state: str):
    """
    Handle Google OAuth callback.
    Exchange code for user info, upsert User in DB, set session cookie.
    """
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _oauth_states.pop(state, None)

    # Exchange code for user info
    user_info = exchange_login_code(code)

    # Upsert user in MongoDB
    user = await User.find_one(User.google_id == user_info["google_id"])
    if user:
        await user.set({
            "email": user_info["email"],
            "name": user_info["name"],
            "avatar_url": user_info.get("avatar_url"),
        })
    else:
        user = User(**user_info)
        await user.insert()

    # Create signed session cookie
    session_token = create_session_token(str(user.id))

    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    """Clear session cookie and redirect to home."""
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_COOKIE)
    return response
