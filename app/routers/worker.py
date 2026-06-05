"""
Worker router — HTTP endpoint to trigger the polling cycle.

Used by:
  - Render.com Cron Job (free tier)
  - Upstash QStash
  - Any external scheduler that sends POST /worker/run

Protected by WORKER_SECRET header to prevent unauthorized triggers.
"""

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import settings
from app.services.polling_service import run_polling_cycle

router = APIRouter(prefix="/worker", tags=["worker"])


@router.post("/run")
async def trigger_polling(
    x_worker_secret: str = Header(None, alias="X-Worker-Secret"),
):
    """
    Trigger one polling cycle.
    Must include header: X-Worker-Secret: <WORKER_SECRET from .env>
    """
    if x_worker_secret != settings.worker_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker secret",
        )

    summary = await run_polling_cycle()
    return {"ok": True, "summary": summary}


@router.get("/health")
async def health_check():
    """Simple health check endpoint for uptime monitoring."""
    return {"status": "ok"}
