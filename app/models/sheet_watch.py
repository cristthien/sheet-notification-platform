from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import Field


class SheetWatch(Document):
    """
    A watched Google Sheet worksheet.
    When new rows are added, notifications are sent via linked NotificationConfigs.
    """

    user_id: PydanticObjectId             # Owner
    spreadsheet_id: str                   # Google Spreadsheet ID (from URL)
    spreadsheet_name: str                 # Display name
    sheet_name: str                       # Worksheet/tab name (e.g. "Sheet1")
    last_row_count: int = 0              # Known row count; new rows = current - this

    is_active: bool = True

    # Configurable per watch (user can adjust via UI)
    # Min: 10s, Max: 3600s, Default: from settings
    poll_interval_seconds: int = 30

    # Audit fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None     # Last error message for dashboard display

    class Settings:
        name = "sheet_watches"
        indexes = [
            "user_id",
            [("user_id", 1), ("is_active", 1)],
        ]
