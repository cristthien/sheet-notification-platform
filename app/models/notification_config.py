from datetime import datetime
from typing import Literal
from beanie import Document, PydanticObjectId
from pydantic import Field


# Supported notification channels
ChannelType = Literal["telegram", "slack", "webhook"]


class NotificationConfig(Document):
    """
    Notification channel configuration attached to a SheetWatch.

    Design: general & extensible — each watch can have multiple configs
    (e.g. HR sheet → HR_bot Telegram + Slack channel).
    Users can reuse the same bot_token across different watches.

    config dict schema by channel_type:
      telegram: {"bot_token": "...", "chat_id": "..."}
      slack:    {"webhook_url": "..."}
      webhook:  {"url": "...", "method": "POST", "headers": {...}}
    """

    watch_id: PydanticObjectId            # Parent SheetWatch
    user_id: PydanticObjectId            # Denormalized for fast queries

    channel_type: ChannelType = "telegram"
    is_active: bool = True

    # Flexible config dict — validated at service layer per channel_type
    config: dict = Field(default_factory=dict)
    # Examples:
    # Telegram: {"bot_token": "123:ABC...", "chat_id": "-100123456"}
    # Slack:    {"webhook_url": "https://hooks.slack.com/..."}
    # Webhook:  {"url": "https://...", "method": "POST", "headers": {"X-Token": "..."}}

    # Optional label for user to distinguish configs in the dashboard
    label: str = ""                       # e.g. "HR Bot", "Sales Alerts"

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "notification_configs"
        indexes = [
            "watch_id",
            "user_id",
            [("watch_id", 1), ("is_active", 1)],
        ]
