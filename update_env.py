from pathlib import Path

ENV_TEXT = """TELEGRAM_BOT_TOKEN=8486218325:AAGkY_gosmgfS3BXkNHLFsR8CD9PWaoyatE
TELEGRAM_TARGET_CHANNEL_ID=@remont_kuvyrkom
WP_SITES_CONFIG=[
  {
    "slug": "test-site",
    "name": "Тестовый сайт",
    "base_url": "https://etecs.ru",
    "username": "m.belonogii",
    "application_password": "kQgkcD@HZ$T$QLZ87R5N4i)V",
    "news_category_id": 81
  }
]
"""


def main() -> None:
    Path(".env").write_text(ENV_TEXT, encoding="utf-8")


if __name__ == "__main__":
    main()

