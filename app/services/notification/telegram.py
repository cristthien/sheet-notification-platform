"""
Telegram notification channel.

Config schema:
    {
        "bot_token": "123456:ABC-DEF...",   # From @BotFather
        "chat_id": "-100123456789"           # Group/channel/user chat ID
    }

How to get chat_id:
    1. Start your bot or add it to a group
    2. Send a message
    3. GET https://api.telegram.org/bot<TOKEN>/getUpdates
    4. Look for "chat": {"id": ...}
"""

import httpx
from app.services.notification.base import BaseNotifier


TELEGRAM_API = "https://api.telegram.org"


class TelegramNotifier(BaseNotifier):

    def validate_config(self, config: dict) -> None:
        required = {"bot_token", "chat_id"}
        missing = required - set(config.keys())
        if missing:
            raise ValueError(
                f"Telegram config missing required keys: {missing}. "
                f"Required: bot_token, chat_id"
            )

    async def send(self, message: str, config: dict) -> bool:
        """Send message via Telegram Bot API."""
        self.validate_config(config)

        bot_token = config["bot_token"]
        chat_id = config["chat_id"]
        url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )

            if resp.status_code == 200:
                return True

            # Log Telegram API error details
            error = resp.json()
            print(
                f"❌ Telegram error {resp.status_code}: "
                f"{error.get('description', 'Unknown error')}"
            )
            return False

        except httpx.TimeoutException:
            print(f"❌ Telegram request timed out for chat_id={chat_id}")
            return False
        except Exception as e:
            print(f"❌ Telegram send error: {e}")
            return False
