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

Создайте файл `.env` (не коммитьте его!):

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
ALLOWED_USER_ID=123456789

WP_SITE_1_URL=https://site1.ru
WP_SITE_1_USER=bot_user
WP_SITE_1_PASS=abcd efgh ijkl mnop qrst uvwx

WP_SITE_2_URL=https://site2.ru
WP_SITE_2_USER=bot_user
WP_SITE_2_PASS=...

WP_SITE_3_URL=https://site3.ru
WP_SITE_3_USER=bot_user
WP_SITE_3_PASS=...