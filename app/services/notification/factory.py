"""
Notification channel factory.

To add a new channel (e.g., Slack):
    1. Create app/services/notification/slack.py with SlackNotifier(BaseNotifier)
    2. Add "slack": SlackNotifier() to NOTIFIERS below
    3. Update ChannelType in models/notification_config.py
    — That's it. No other changes needed.
"""

from app.services.notification.base import BaseNotifier
from app.services.notification.telegram import TelegramNotifier

# Registry of available notification channels
NOTIFIERS: dict[str, BaseNotifier] = {
    "telegram": TelegramNotifier(),
    # "slack": SlackNotifier(),       ← uncomment when ready
    # "webhook": WebhookNotifier(),   ← uncomment when ready
}


def get_notifier(channel_type: str) -> BaseNotifier:
    """
    Get a notifier instance by channel type.
    Raises ValueError if channel_type is not registered.
    """
    notifier = NOTIFIERS.get(channel_type)
    if notifier is None:
        raise ValueError(
            f"Unknown notification channel: '{channel_type}'. "
            f"Available: {list(NOTIFIERS.keys())}"
        )
    return notifier


def get_available_channels() -> list[str]:
    """Returns list of currently supported channel types."""
    return list(NOTIFIERS.keys())
