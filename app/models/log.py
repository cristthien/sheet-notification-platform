from datetime import datetime
from typing import Optional, Literal
from beanie import Document, PydanticObjectId
from pydantic import Field


LogStatus = Literal["success", "failed", "skipped"]


class Log(Document):
    """
    Immutable audit log for every notification attempt.
    Records: what row was added, when, which channel, and whether it succeeded.
    """

    # References
    watch_id: PydanticObjectId
    user_id: PydanticObjectId
    notification_config_id: PydanticObjectId

    # Row data
    row_index: int                        # 1-based row number in the sheet
    row_data: dict                        # {"Column A": "value", "Column B": "value"}
    spreadsheet_id: str
    sheet_name: str

    # Notification result
    channel_type: str
    status: LogStatus
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "logs"
        indexes = [
            # Fast queries for dashboard log view
            [("user_id", 1), ("created_at", -1)],
            [("watch_id", 1), ("created_at", -1)],
            # Status filter
            [("user_id", 1), ("status", 1), ("created_at", -1)],
        ]
