"""Abstract base class for all notification channels."""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """
    All notification channels must implement this interface.
    New channels (Slack, Email, Webhook) just need to subclass this.
    """

    @abstractmethod
    async def send(self, message: str, config: dict) -> bool:
        """
        Send a notification message.

        Args:
            message: Formatted message text (may contain HTML for Telegram)
            config:  Channel-specific configuration dict

        Returns:
            True if sent successfully, False otherwise
        """
        ...

    @abstractmethod
    def validate_config(self, config: dict) -> None:
        """
        Validate that required config keys are present.
        Raise ValueError with descriptive message if invalid.
        """
        ...
