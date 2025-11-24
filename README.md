# Echelon News Helper Bot

Telegram-бот, который помогает подготовить и мгновенно опубликовать новость сразу на нескольких площадках: трёх сайтах на WordPress (рубрика «Новости») и в Telegram‑канале.

## Возможности

- Последовательный сбор заголовка, отрывка, полного текста и изображения.
- Выбор одной или нескольких площадок для публикации (WordPress сайты и/или канал).
- Публикация в WordPress через REST API (создание записи и загрузка изображения как `featured_media`).
- Публикация в канал Telegram с изображением и отдельным текстовым сообщением.
- Ограничение доступа по whitelisting (опционально).

## Настройка окружения

Создайте файл `.env` (или задайте переменные среды любым удобным способом):

```bash
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_TARGET_CHANNEL_ID=@your_channel
WP_SITES_CONFIG=[
  {
    "slug": "site1",
    "name": "АО Эшелон Технологии",
    "base_url": "https://example.com",
    "username": "m.belonogii",
    "application_password": "kQgkcD@HZ$T$QLZ87R5N4i)V",
    "news_category_id": 12
  },
  {
    "slug": "site2",
    "name": "Сайт №2",
    "base_url": "https://example.net",
    "username": "bot-user",
    "application_password": "....",
    "news_category_id": 34
  }
]
# необязательно, но можно ограничить доступ
ALLOWED_CHAT_IDS=123456789,987654321
```

> **Как получить `news_category_id`?** В админке WordPress зайдите в «Рубрики», наведите на «Новости» и скопируйте `tag_ID` из ссылки.

## Локальный запуск

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
python -m src.bot
```

Бот запустится и начнёт polling Telegram API. Введите `/start`, чтобы пройти сценарий публикации.

## Docker

```bash
docker build -t echelon-news-helper .
docker run --rm -it --env-file .env echelon-news-helper
```

Контейнер использует `python:3.11-slim`, поэтому его легко развернуть на любой платформе.

## Развёртывание на Render

1. Создайте **Docker**-службу на [Render](https://render.com/).
2. Укажите репозиторий GitHub, выберите регион и тариф, задайте необходимые переменные окружения.
3. Настройте Health Check (необязательно) и задействуйте авто-деплой при пуше в ветку.
4. Render автоматически построит образ и запустит контейнер (zero-downtime деплой, автоскейлинг и приватная сеть доступны из коробки). [Источник](https://render.com/)

## Архитектура кода

- `src/config.py` — парсинг конфигурации из переменных окружения.
- `src/wordpress_client.py` — минимальный клиент для загрузки медиа и создания постов.
- `src/bot.py` — сценарий Telegram-бота (ConversationHandler) и сервис публикации.

## Дальнейшие улучшения

- Автогенерация предпросмотра (например, Markdown → HTML).
- Поддержка отложенных публикаций и драфтов.
- Хранение истории публикаций в базе данных.

