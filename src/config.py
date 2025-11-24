from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Sequence

from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv


class WordPressSiteConfig(BaseModel):
    """Configuration required to publish to a WordPress site."""

    slug: str = Field(..., description="Internal identifier used in the bot UI.")
    name: str = Field(..., description="Human readable name of the site.")
    base_url: str = Field(..., description="Base URL of the WordPress site, e.g. https://example.com")
    username: str = Field(..., description="WordPress username tied to an application password.")
    application_password: str = Field(..., description="WordPress application password for REST auth.")
    news_category_id: int = Field(..., description="Category ID for the 'Новости' rubric.")


class TelegramChannelConfig(BaseModel):
    """Target Telegram channel details."""

    channel_id: str = Field(..., description="Channel identifier (e.g. @channelname or numeric ID).")
    publish_enabled: bool = Field(True, description="Allow publishing to the channel.")


class AppConfig(BaseModel):
    """Full application configuration."""

    bot_token: str = Field(..., alias="telegram_bot_token")
    wordpress_sites: List[WordPressSiteConfig]
    telegram_channel: TelegramChannelConfig
    allowed_chat_ids: Sequence[int] | None = Field(
        default=None,
        description="Optional list of chat IDs allowed to interact with the bot.",
    )

    @property
    def sites_by_slug(self) -> dict[str, WordPressSiteConfig]:
        return {site.slug: site for site in self.wordpress_sites}


def parse_wordpress_sites(raw_value: str | None) -> List[WordPressSiteConfig]:
    """Parse JSON encoded WordPress configuration."""
    if not raw_value:
        return []

    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("WP_SITES_CONFIG is not valid JSON") from exc

    if not isinstance(payload, list):
        raise ValueError("WP_SITES_CONFIG must be a JSON array")

    return [WordPressSiteConfig(**item) for item in payload]


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    load_dotenv()
    from os import getenv

    raw_sites = getenv("WP_SITES_CONFIG")
    telegram_channel_id = getenv("TELEGRAM_TARGET_CHANNEL_ID")
    if not telegram_channel_id:
        raise ValueError("TELEGRAM_TARGET_CHANNEL_ID is required")

    bot_token = getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    telegram_channel = TelegramChannelConfig(channel_id=telegram_channel_id)
    raw_allowed = getenv("ALLOWED_CHAT_IDS")
    allowed_ids: Sequence[int] | None = None
    if raw_allowed:
        allowed_ids = tuple(int(item.strip()) for item in raw_allowed.split(",") if item.strip())

    try:
        return AppConfig(
            telegram_bot_token=bot_token,
            wordpress_sites=parse_wordpress_sites(raw_sites),
            telegram_channel=telegram_channel,
            allowed_chat_ids=allowed_ids,
        )
    except ValidationError as exc:
        raise ValueError(f"Configuration error: {exc}") from exc


@lru_cache(maxsize=1)
def get_cached_config() -> AppConfig:
    """Expose cached config for modules that need it."""
    return load_config()

