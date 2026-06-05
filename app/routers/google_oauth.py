"""
Google Sheets OAuth router.
Separate from login — connects user's Google Sheets access.

Routes:
    GET /google/authorize   → redirect to Google Sheets consent
    GET /google/callback    → store Sheets credentials on User
    GET /google/disconnect  → revoke and clear Sheets credentials
    GET /google/sheets      → list user's spreadsheets (JSON API)
    GET /google/worksheets  → list worksheets in a spreadsheet (JSON API)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.security import get_current_user_id
from app.models.user import User
from app.services.google_service import (
    exchange_sheets_code,
    get_sheets_authorization_url,
)
from app.services.sheets_service import list_spreadsheets, list_worksheets

router = APIRouter(prefix="/google", tags=["google"])

_oauth_states: dict[str, str] = {}


@router.get("/authorize")
async def authorize_sheets(user_id: str = Depends(get_current_user_id)):
    """Start the Google Sheets OAuth flow."""
    auth_url, state = get_sheets_authorization_url()
    _oauth_states[state] = user_id
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def sheets_callback(code: str, state: str):
    """
    Handle Google Sheets OAuth callback.
    Store access/refresh tokens on the User document.
    """
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token_data = exchange_sheets_code(code)
    await user.set(token_data)

    return RedirectResponse(url="/dashboard?sheets_connected=1")


@router.get("/disconnect")
async def disconnect_sheets(user_id: str = Depends(get_current_user_id)):
    """Disconnect Google Sheets — clear stored credentials."""
    from app.models.sheet_watch import SheetWatch

    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await user.set({
        "sheets_access_token": None,
        "sheets_refresh_token": None,
        "sheets_token_expiry": None,
        "sheets_connected": False,
        "sheets_revoked": False,
    })

    # Pause all watches
    await SheetWatch.find(
        SheetWatch.user_id == user.id
    ).update({"$set": {"is_active": False}})

    return RedirectResponse(url="/dashboard")


@router.get("/spreadsheets")
async def list_user_spreadsheets(user_id: str = Depends(get_current_user_id)):
    """List all Google Spreadsheets accessible to the user."""
    user = await User.get(user_id)
    if not user or not user.sheets_connected:
        raise HTTPException(status_code=403, detail="Google Sheets not connected")

    try:
        sheets = await list_spreadsheets(user)
        return {"spreadsheets": sheets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/worksheets")
async def list_sheet_tabs(
    spreadsheet_id: str = Query(...),
    user_id: str = Depends(get_current_user_id),
):
    """List all worksheet tabs in a given spreadsheet."""
    user = await User.get(user_id)
    if not user or not user.sheets_connected:
        raise HTTPException(status_code=403, detail="Google Sheets not connected")

    try:
        worksheets = await list_worksheets(user, spreadsheet_id)
        return {"worksheets": worksheets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
