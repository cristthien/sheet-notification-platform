"""
Standalone background worker for Render.com Worker dyno.

This script runs separately from the FastAPI web service.
It initializes MongoDB and runs the polling cycle on a schedule.

Usage:
    python worker.py

Deploy on Render.com:
    - Type: Background Worker
    - Command: python worker.py
    - Environment: set USE_SCHEDULER=false on the Web Service
      (so only the worker dyno does the polling)
"""

import asyncio
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import init_db
from app.services.polling_service import run_polling_cycle


async def main():
    print("🚀 Sheet Notifier Worker starting...")
    await init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_polling_cycle,
        "interval",
        seconds=settings.default_poll_interval,
        id="polling_cycle",
        replace_existing=True,
    )
    scheduler.start()
    print(f"⏰ Polling every {settings.default_poll_interval} seconds")

    # Run once immediately on startup
    await run_polling_cycle()

    # Keep alive until SIGTERM
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        print("\n🛑 Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await stop_event.wait()
    scheduler.shutdown(wait=False)
    print("✅ Worker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
