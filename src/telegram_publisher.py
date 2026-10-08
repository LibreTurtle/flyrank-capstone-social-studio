import httpx

from publishers import PublishFailure, PublishResult


class TelegramPublisher:
    name = "telegram"

    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.transport = transport

    def publish(self, *, text: str, idempotency_key: str) -> PublishResult:
        if not self.bot_token or not self.chat_id:
            raise PublishFailure(
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before publishing."
            )

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            with httpx.Client(timeout=15.0, transport=self.transport) as client:
                response = client.post(
                    api_url,
                    json={"chat_id": self.chat_id, "text": text},
                )
        except httpx.HTTPError as error:
            raise PublishFailure(
                "Telegram did not confirm delivery. Check the channel before retrying.",
                uncertain=True,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise PublishFailure(
                "Telegram returned an unreadable response. Check the channel before retrying.",
                uncertain=True,
            ) from error

        if not payload.get("ok"):
            description = payload.get("description", "Telegram rejected the message")
            raise PublishFailure(f"Telegram rejected the message: {description}")

        try:
            message = payload["result"]
            remote_reference = f"{message['chat']['id']}:{message['message_id']}"
        except (KeyError, TypeError) as error:
            raise PublishFailure(
                "Telegram accepted the request but did not return a message reference.",
                uncertain=True,
            ) from error

        return PublishResult(remote_reference=remote_reference, preview=text)
