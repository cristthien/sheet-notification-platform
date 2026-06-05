"""
FastAPI application entry point.

Startup sequence:
  1. Connect to MongoDB Atlas + init beanie ODM
  2. Mount static files
  3. Start APScheduler background polling (local dev mode)
  4. Register all routers
"""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import init_db
from app.core.security import get_current_user_id
from app.models.log import Log
from app.models.sheet_watch import SheetWatch
from app.models.user import User
from app.routers import auth, google_oauth, sheets, logs, worker
from app.services.polling_service import run_polling_cycle

# APScheduler instance (used in local/Render dev mode)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Connect DB
    await init_db()

    # Start background scheduler (only when not using external Cron)
    use_scheduler = os.getenv("USE_SCHEDULER", "true").lower() == "true"
    if use_scheduler:
        # Per-watch interval is handled inside run_polling_cycle;
        # the scheduler runs a global cycle every DEFAULT_POLL_INTERVAL seconds.
        scheduler.add_job(
            run_polling_cycle,
            "interval",
            seconds=settings.default_poll_interval,
            id="polling_cycle",
            replace_existing=True,
        )
        scheduler.start()
        print(f"⏰ Scheduler started (every {settings.default_poll_interval}s)")

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("⏰ Scheduler stopped")


app = FastAPI(
    title="Sheet Notifier Platform",
    description="Automatically send notifications when new rows are added to Google Sheets",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(auth.router)
app.include_router(google_oauth.router)
app.include_router(sheets.router)
app.include_router(logs.router)
app.include_router(worker.router)


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home / login page."""
    token = request.cookies.get("snp_session")
    if token:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Main dashboard page."""
    user = await User.get(user_id)
    if not user:
        return RedirectResponse(url="/auth/logout")

    # Stats for dashboard
    watches = await SheetWatch.find(SheetWatch.user_id == user.id).to_list()
    from beanie import PydanticObjectId
    from datetime import datetime, timedelta

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total_logs_today = await Log.find({
        "user_id": PydanticObjectId(user_id),
        "created_at": {"$gte": today_start},
    }).count()
    success_today = await Log.find({
        "user_id": PydanticObjectId(user_id),
        "created_at": {"$gte": today_start},
        "status": "success",
    }).count()

    recent_logs = (
        await Log.find({"user_id": PydanticObjectId(user_id)})
        .sort(-Log.created_at)
        .limit(5)
        .to_list()
    )

    sheets_connected = query_param = request.query_params.get("sheets_connected")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "watches": watches,
        "active_watches": sum(1 for w in watches if w.is_active),
        "total_logs_today": total_logs_today,
        "success_today": success_today,
        "recent_logs": recent_logs,
        "just_connected": sheets_connected == "1",
    })
