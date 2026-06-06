import asyncio
from app.core.database import init_db
from app.models.sheet_watch import SheetWatch
from app.models.notification_config import NotificationConfig

async def main():
    await init_db()
    watches = await SheetWatch.find_all().to_list()
    print(f"Total watches: {len(watches)}")
    for w in watches:
        print(f"Watch: {w.id} - {w.spreadsheet_name} - {w.sheet_name} (Active: {w.is_active})")
        configs = await NotificationConfig.find(NotificationConfig.watch_id == w.id).to_list()
        print(f"  Configs: {len(configs)}")
        for c in configs:
            print(f"    - {c.id} ({c.channel_type}) (Active: {c.is_active})")

asyncio.run(main())
