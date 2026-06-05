"""
Logs router — view notification history.

Routes:
    GET /logs         → HTML page with log table
    GET /logs/data    → JSON API for HTMX partial updates
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Query
from fastapi.templating import Jinja2Templates

from app.core.security import get_current_user_id
from app.models.log import Log
from app.models.sheet_watch import SheetWatch
from app.models.user import User

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 50


@router.get("")
async def logs_page(
    request: Request,
    watch_id: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    user_id: str = Depends(get_current_user_id),
):
    user = await User.get(user_id)
    logs, total = await _fetch_logs(user_id, watch_id, status, page)
    watches = await SheetWatch.find(SheetWatch.user_id == user.id).to_list()

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "user": user,
        "logs": logs,
        "watches": watches,
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "selected_watch": watch_id,
        "selected_status": status,
    })


@router.get("/data")
async def logs_data(
    watch_id: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    user_id: str = Depends(get_current_user_id),
):
    """JSON endpoint for HTMX log table refresh."""
    logs, total = await _fetch_logs(user_id, watch_id, status, page)
    return {
        "logs": [
            {
                "id": str(log.id),
                "sheet_name": log.sheet_name,
                "row_index": log.row_index,
                "row_data": log.row_data,
                "channel_type": log.channel_type,
                "status": log.status,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
    }


async def _fetch_logs(
    user_id: str,
    watch_id: str | None,
    status: str | None,
    page: int,
):
    """Build and execute the log query."""
    from beanie import PydanticObjectId

    query = {"user_id": PydanticObjectId(user_id)}
    if watch_id:
        query["watch_id"] = PydanticObjectId(watch_id)
    if status:
        query["status"] = status

    total = await Log.find(query).count()
    logs = (
        await Log.find(query)
        .sort(-Log.created_at)
        .skip((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .to_list()
    )
    return logs, total
