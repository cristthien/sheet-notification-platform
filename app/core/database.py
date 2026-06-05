import motor.motor_asyncio
from beanie import init_beanie

from app.core.config import settings
from app.models.user import User
from app.models.sheet_watch import SheetWatch
from app.models.notification_config import NotificationConfig
from app.models.log import Log


async def init_db():
    """Initialize MongoDB connection and beanie ODM."""
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    await init_beanie(
        database=db,
        document_models=[User, SheetWatch, NotificationConfig, Log],
    )
    print(f"✅ MongoDB connected: {settings.mongodb_db_name}")
    return client
