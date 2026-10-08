import os

from mock_publisher import MockLinkedInPublisher, MockXPublisher
from publishers import SocialPublisher
from telegram_publisher import TelegramPublisher


def configured_publisher(platform: str) -> SocialPublisher:
    name = os.getenv("SOCIAL_PUBLISHER", "").strip() or platform
    if name == "telegram":
        return TelegramPublisher(
            os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        )
    if name == "mock_x":
        return MockXPublisher()
    if name == "mock_linkedin":
        return MockLinkedInPublisher()
    raise ValueError(f"Unknown publisher adapter '{name}'")
