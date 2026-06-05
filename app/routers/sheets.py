"""
Sheet Watches router — CRUD for SheetWatch + NotificationConfig.

Routes:
    GET    /watches              → list user's watches (HTML page)
    POST   /watches              → create new watch
    DELETE /watches/{watch_id}   → delete watch
    PATCH  /watches/{watch_id}/toggle → toggle active/inactive

    POST   /watches/{watch_id}/notifications        → add notification config
    DELETE /watches/{watch_id}/notifications/{cfg_id} → remove config
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from beanie import PydanticObjectId

from app.core.security import get_current_user_id
from app.models.notification_config import NotificationConfig
from app.models.sheet_watch import SheetWatch
from app.models.user import User
from app.services.notification.factory import get_notifier, get_available_channels
from app.services.sheets_service import (
    get_spreadsheet_name,
    get_current_row_count,
)

router = APIRouter(prefix="/watches", tags=["watches"])
templates = Jinja2Templates(directory="app/templates")


# ─── Pages ────────────────────────────────────────────────────────────────────

@router.get("")
async def watches_page(request: Request, user_id: str = Depends(get_current_user_id)):
    user = await User.get(user_id)
    watches = await SheetWatch.find(SheetWatch.user_id == user.id).to_list()

    # Fetch notification configs per watch
    watch_configs = {}
    for w in watches:
        configs = await NotificationConfig.find(
            NotificationConfig.watch_id == w.id
        ).to_list()
        watch_configs[str(w.id)] = configs

    return templates.TemplateResponse("watches.html", {
        "request": request,
        "user": user,
        "watches": watches,
        "watch_configs": watch_configs,
        "available_channels": get_available_channels(),
    })


# ─── Watch CRUD ───────────────────────────────────────────────────────────────

@router.post("")
async def create_watch(
    spreadsheet_id: str = Form(...),
    sheet_name: str = Form(...),
    poll_interval_seconds: int = Form(30),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new SheetWatch."""
    user = await User.get(user_id)
    if not user or not user.sheets_connected:
        raise HTTPException(status_code=403, detail="Connect Google Sheets first")

    # Validate interval bounds
    poll_interval_seconds = max(10, min(3600, poll_interval_seconds))

    # Get spreadsheet name for display
    try:
        spreadsheet_name = await get_spreadsheet_name(user, spreadsheet_id)
        # Initialize last_row_count to current count (don't spam old rows)
        initial_count = await get_current_row_count(user, spreadsheet_id, sheet_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot access sheet: {e}")

    watch = SheetWatch(
        user_id=user.id,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_name=spreadsheet_name,
        sheet_name=sheet_name,
        last_row_count=initial_count,
        poll_interval_seconds=poll_interval_seconds,
    )
    await watch.insert()

    return RedirectResponse(url="/watches", status_code=303)


@router.delete("/{watch_id}")
async def delete_watch(
    watch_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a watch and all its notification configs."""
    watch = await SheetWatch.get(watch_id)
    if not watch or str(watch.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Watch not found")

    # Delete associated configs
    await NotificationConfig.find(
        NotificationConfig.watch_id == watch.id
    ).delete()

    await watch.delete()
    return {"ok": True}


@router.patch("/{watch_id}/toggle")
async def toggle_watch(
    watch_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Toggle a watch active/inactive."""
    watch = await SheetWatch.get(watch_id)
    if not watch or str(watch.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Watch not found")

    await watch.set({"is_active": not watch.is_active})
    return {"is_active": watch.is_active}


# ─── Notification Config CRUD ─────────────────────────────────────────────────

@router.post("/{watch_id}/notifications")
async def add_notification_config(
    watch_id: str,
    channel_type: str = Form(...),
    label: str = Form(""),
    # Telegram fields
    bot_token: str = Form(""),
    chat_id: str = Form(""),
    # Webhook fields
    webhook_url: str = Form(""),
    user_id: str = Depends(get_current_user_id),
):
    """Add a notification config to a watch."""
    watch = await SheetWatch.get(watch_id)
    if not watch or str(watch.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Watch not found")

    # Build config dict based on channel_type
    if channel_type == "telegram":
        config = {"bot_token": bot_token.strip(), "chat_id": chat_id.strip()}
    elif channel_type == "slack":
        config = {"webhook_url": webhook_url.strip()}
    elif channel_type == "webhook":
        config = {"url": webhook_url.strip(), "method": "POST", "headers": {}}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel_type}")

    # Validate config via notifier
    try:
        notifier = get_notifier(channel_type)
        notifier.validate_config(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    nc = NotificationConfig(
        watch_id=watch.id,
        user_id=watch.user_id,
        channel_type=channel_type,
        config=config,
        label=label or channel_type.title(),
    )
    await nc.insert()

    return RedirectResponse(url="/watches", status_code=303)


@router.delete("/{watch_id}/notifications/{config_id}")
async def delete_notification_config(
    watch_id: str,
    config_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a notification config."""
    nc = await NotificationConfig.get(config_id)
    if not nc or str(nc.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Config not found")

    await nc.delete()
    return {"ok": True}
