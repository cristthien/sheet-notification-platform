"""
Core polling service.

run_polling_cycle() is the central function called by:
  - APScheduler (local dev / Render.com worker dyno)
  - POST /worker/run HTTP endpoint (Cron Job trigger)

Flow:
  1. Fetch all active SheetWatches
  2. For each watch, check if new rows were added
  3. For each new row, send notifications via all active NotificationConfigs
  4. Save Log entries for every attempt (success or failure)
  5. Update last_row_count on the watch
"""

from datetime import datetime
from typing import Optional

from app.models.log import Log
from app.models.notification_config import NotificationConfig
from app.models.sheet_watch import SheetWatch
from app.models.user import User
from app.services.google_service import TokenRevokedException, get_valid_credentials
from app.services.notification.factory import get_notifier
import gspread


def _format_message(
    row_data: dict,
    watch: SheetWatch,
    row_index: int,
) -> str:
    """Format a Telegram-friendly HTML message for a new row."""
    lines = [
        f"📊 <b>New entry in your Google Sheet!</b>",
        f"",
        f"📋 <b>Sheet:</b> {watch.spreadsheet_name} → {watch.sheet_name}",
        f"🔢 <b>Row:</b> #{row_index}",
        f"",
        f"<b>Data:</b>",
    ]

    for key, value in row_data.items():
        if value:  # Skip empty cells
            lines.append(f"  • <b>{key}:</b> {value}")

    lines += [
        f"",
        f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ]

    return "\n".join(lines)


async def run_polling_cycle() -> dict:
    """
    Main polling cycle. Checks all active watches for new rows.
    Returns a summary dict for logging/monitoring.
    """
    summary = {
        "started_at": datetime.utcnow().isoformat(),
        "watches_checked": 0,
        "new_rows_found": 0,
        "notifications_sent": 0,
        "notifications_failed": 0,
        "errors": [],
    }

    # Fetch all active watches
    active_watches = await SheetWatch.find(
        SheetWatch.is_active == True
    ).to_list()

    summary["watches_checked"] = len(active_watches)
    print(f"🔍 Polling {len(active_watches)} active watches...")

    for watch in active_watches:
        try:
            await _process_watch(watch, summary)
        except Exception as e:
            error_msg = f"Watch {watch.id} ({watch.spreadsheet_name}): {str(e)}"
            summary["errors"].append(error_msg)
            print(f"❌ {error_msg}")
            await watch.set({"last_error": str(e)[:500]})

    summary["finished_at"] = datetime.utcnow().isoformat()
    print(
        f"✅ Polling done: {summary['new_rows_found']} new rows, "
        f"{summary['notifications_sent']} sent, "
        f"{summary['notifications_failed']} failed"
    )
    return summary


async def _process_watch(watch: SheetWatch, summary: dict) -> None:
    """Process a single SheetWatch — detect new rows and notify."""

    # Get user and validate their credentials
    user = await User.get(watch.user_id)
    if not user:
        await watch.set({"is_active": False, "last_error": "User not found"})
        return

    # Get valid (auto-refreshed) credentials
    try:
        creds = await get_valid_credentials(user)
    except TokenRevokedException:
        # handle_revoke already called inside get_valid_credentials
        return

    # Read sheet data
    try:
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(watch.spreadsheet_id)
        worksheet = spreadsheet.worksheet(watch.sheet_name)
        all_rows = worksheet.get_all_records()
    except gspread.exceptions.SpreadsheetNotFound:
        await watch.set({
            "is_active": False,
            "last_error": "Spreadsheet not found or access denied",
        })
        return
    except Exception as e:
        raise RuntimeError(f"Failed to read sheet: {e}")

    current_count = len(all_rows)

    if current_count <= watch.last_row_count:
        # No new rows
        await watch.set({"last_checked_at": datetime.utcnow(), "last_error": None})
        return

    # New rows detected!
    new_rows = all_rows[watch.last_row_count:]
    summary["new_rows_found"] += len(new_rows)
    print(f"  🆕 {len(new_rows)} new row(s) in '{watch.spreadsheet_name} / {watch.sheet_name}'")

    # Get active notification configs for this watch
    configs = await NotificationConfig.find(
        NotificationConfig.watch_id == watch.id,
        NotificationConfig.is_active == True,
    ).to_list()

    if not configs:
        print(f"  ⚠️  No active notification configs for watch {watch.id}")

    # Send notification for each new row × each config
    for i, row_data in enumerate(new_rows):
        row_index = watch.last_row_count + i + 2  # +2: 1 for header, 1 for 1-based
        message = _format_message(row_data, watch, row_index)

        for config in configs:
            success = False
            error_msg = None

            try:
                notifier = get_notifier(config.channel_type)
                success = await notifier.send(message, config.config)
            except Exception as e:
                error_msg = str(e)
                success = False

            # Always log the attempt
            log = Log(
                watch_id=watch.id,
                user_id=user.id,
                notification_config_id=config.id,
                row_index=row_index,
                row_data=row_data,
                spreadsheet_id=watch.spreadsheet_id,
                sheet_name=watch.sheet_name,
                channel_type=config.channel_type,
                status="success" if success else "failed",
                sent_at=datetime.utcnow() if success else None,
                error_message=error_msg,
            )
            await log.insert()

            if success:
                summary["notifications_sent"] += 1
            else:
                summary["notifications_failed"] += 1
                print(f"  ❌ Notification failed: {error_msg}")

    # Update watch state
    await watch.set({
        "last_row_count": current_count,
        "last_checked_at": datetime.utcnow(),
        "last_error": None,
    })
