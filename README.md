# 📰 Telegram-бот для публикации новостей в WordPress

Этот бот принимает от вас в Telegram:
- Заголовок новости  
- Анонс (краткое описание)  
- Полный текст  
- Изображение  

…и автоматически публикует запись **на трёх ваших WordPress-сайтах**.

Проект разработан для размещения на **Render.com** с использованием **Docker** и **webhook-режима**.

---

## 🧩 Возможности

- Публикация на нескольких WordPress-сайтах одновременно  
- Поддержка изображений (становятся featured image)  
- Защита по Telegram ID (только вы можете использовать бота)  
- Минималистичный и надёжный код на Python  
- Готов к деплою на Render (бесплатный тариф)  
- Выбор площадок перед публикацией (каждый сайт и Telegram-канал можно включать/отключать)
- Планирование даты публикации на WordPress-сайтах

---

## 🛠 Требования

- Аккаунт Telegram и бот (токен от [@BotFather](https://t.me/BotFather))  
- Три WordPress-сайта с включённым REST API  
- Учётные данные с **Application Passwords** для каждого сайта  
- Аккаунт на [Render.com](https://render.com)  

> ⚠️ Убедитесь, что на ваших WordPress-сайтах **работает**:  
> `https://ваш-сайт.ru/wp-json/wp/v2/posts`

---

## ⚙️ Настройка

### 1. Переменные окружения

Создайте файл `.env` (не коммитьте его!) и заполните минимум:

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_TARGET_CHANNEL_ID=@your_channel   # если нужно публиковать в канал
ALLOWED_USER_ID=123456789

# WordPress сайт №1
WP_SITE_1_NAME=Сайт 1
WP_SITE_1_SLUG=site1
WP_SITE_1_URL=https://site1.ru
WP_SITE_1_USER=bot_user
WP_SITE_1_PASS=abcd efgh ijkl mnop qrst uvwx
WP_SITE_1_CATEGORY_ID=12

# WordPress сайт №2
WP_SITE_2_URL=https://site2.ru
WP_SITE_2_USER=bot_user
WP_SITE_2_PASS=...
WP_SITE_2_CATEGORY_ID=34

# WordPress сайт №3
WP_SITE_3_URL=https://site3.ru
WP_SITE_3_USER=bot_user
WP_SITE_3_PASS=...
WP_SITE_3_CATEGORY_ID=56
```

> ⚠️ ID рубрики (news_category_id) можно посмотреть в админке WordPress: наведите на «Новости» и скопируйте `tag_ID` из ссылки. Для каждого сайта укажите свой `WP_SITE_X_CATEGORY_ID`.

После ввода полного текста бот попросит указать дату публикации для сайтов. Введите `YYYY-MM-DD HH:MM` (по местному времени) или напишите `сейчас`, чтобы опубликовать немедленно. Telegram-пост формируется из заголовка, анонса и полного текста в одном сообщении с корректным форматированием ссылок и списков.
