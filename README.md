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
# рџ“° Telegram-Р±РѕС‚ РґР»СЏ РїСѓР±Р»РёРєР°С†РёРё РЅРѕРІРѕСЃС‚РµР№ РІ WordPress

Р­С‚РѕС‚ Р±РѕС‚ РїСЂРёРЅРёРјР°РµС‚ РѕС‚ РІР°СЃ РІ Telegram:
- Р—Р°РіРѕР»РѕРІРѕРє РЅРѕРІРѕСЃС‚Рё  
- РђРЅРѕРЅСЃ (РєСЂР°С‚РєРѕРµ РѕРїРёСЃР°РЅРёРµ)  
- РџРѕР»РЅС‹Р№ С‚РµРєСЃС‚  
- РР·РѕР±СЂР°Р¶РµРЅРёРµ  

вЂ¦Рё Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РїСѓР±Р»РёРєСѓРµС‚ Р·Р°РїРёСЃСЊ **РЅР° С‚СЂС‘С… РІР°С€РёС… WordPress-СЃР°Р№С‚Р°С…**.

РџСЂРѕРµРєС‚ СЂР°Р·СЂР°Р±РѕС‚Р°РЅ РґР»СЏ СЂР°Р·РјРµС‰РµРЅРёСЏ РЅР° **Render.com** СЃ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµРј **Docker** Рё **webhook-СЂРµР¶РёРјР°**.

---

## рџ§© Р’РѕР·РјРѕР¶РЅРѕСЃС‚Рё

- РџСѓР±Р»РёРєР°С†РёСЏ РЅР° РЅРµСЃРєРѕР»СЊРєРёС… WordPress-СЃР°Р№С‚Р°С… РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ  
- РџРѕРґРґРµСЂР¶РєР° РёР·РѕР±СЂР°Р¶РµРЅРёР№ (СЃС‚Р°РЅРѕРІСЏС‚СЃСЏ featured image)  
- Р—Р°С‰РёС‚Р° РїРѕ Telegram ID (С‚РѕР»СЊРєРѕ РІС‹ РјРѕР¶РµС‚Рµ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ Р±РѕС‚Р°)  
- РњРёРЅРёРјР°Р»РёСЃС‚РёС‡РЅС‹Р№ Рё РЅР°РґС‘Р¶РЅС‹Р№ РєРѕРґ РЅР° Python  
- Р“РѕС‚РѕРІ Рє РґРµРїР»РѕСЋ РЅР° Render (Р±РµСЃРїР»Р°С‚РЅС‹Р№ С‚Р°СЂРёС„)  
- Р’С‹Р±РѕСЂ РїР»РѕС‰Р°РґРѕРє РїРµСЂРµРґ РїСѓР±Р»РёРєР°С†РёРµР№ (РєР°Р¶РґС‹Р№ СЃР°Р№С‚ Рё Telegram-РєР°РЅР°Р» РјРѕР¶РЅРѕ РІРєР»СЋС‡Р°С‚СЊ/РѕС‚РєР»СЋС‡Р°С‚СЊ)

---

## рџ›  РўСЂРµР±РѕРІР°РЅРёСЏ

- РђРєРєР°СѓРЅС‚ Telegram Рё Р±РѕС‚ (С‚РѕРєРµРЅ РѕС‚ [@BotFather](https://t.me/BotFather))  
- РўСЂРё WordPress-СЃР°Р№С‚Р° СЃ РІРєР»СЋС‡С‘РЅРЅС‹Рј REST API  
- РЈС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ СЃ **Application Passwords** РґР»СЏ РєР°Р¶РґРѕРіРѕ СЃР°Р№С‚Р°  
- РђРєРєР°СѓРЅС‚ РЅР° [Render.com](https://render.com)  

> вљ пёЏ РЈР±РµРґРёС‚РµСЃСЊ, С‡С‚Рѕ РЅР° РІР°С€РёС… WordPress-СЃР°Р№С‚Р°С… **СЂР°Р±РѕС‚Р°РµС‚**:  
> `https://РІР°С€-СЃР°Р№С‚.ru/wp-json/wp/v2/posts`

---

## вљ™пёЏ РќР°СЃС‚СЂРѕР№РєР°

### 1. РџРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ

РЎРѕР·РґР°Р№С‚Рµ С„Р°Р№Р» `.env` (РЅРµ РєРѕРјРјРёС‚СЊС‚Рµ РµРіРѕ!) Рё Р·Р°РїРѕР»РЅРёС‚Рµ РјРёРЅРёРјСѓРј:

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_TARGET_CHANNEL_ID=@your_channel   # РµСЃР»Рё РЅСѓР¶РЅРѕ РїСѓР±Р»РёРєРѕРІР°С‚СЊ РІ РєР°РЅР°Р»
ALLOWED_USER_ID=123456789

# WordPress СЃР°Р№С‚ в„–1
WP_SITE_1_NAME=РЎР°Р№С‚ 1
WP_SITE_1_SLUG=site1
WP_SITE_1_URL=https://site1.ru
WP_SITE_1_USER=bot_user
WP_SITE_1_PASS=abcd efgh ijkl mnop qrst uvwx
WP_SITE_1_CATEGORY_ID=12

# WordPress СЃР°Р№С‚ в„–2
WP_SITE_2_URL=https://site2.ru
WP_SITE_2_USER=bot_user
WP_SITE_2_PASS=...
WP_SITE_2_CATEGORY_ID=34

# WordPress СЃР°Р№С‚ в„–3
WP_SITE_3_URL=https://site3.ru
WP_SITE_3_USER=bot_user
WP_SITE_3_PASS=...
WP_SITE_3_CATEGORY_ID=56
```

> вљ пёЏ ID СЂСѓР±СЂРёРєРё (news_category_id) РјРѕР¶РЅРѕ РїРѕСЃРјРѕС‚СЂРµС‚СЊ РІ Р°РґРјРёРЅРєРµ WordPress: РЅР°РІРµРґРёС‚Рµ РЅР° В«РќРѕРІРѕСЃС‚РёВ» Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ `tag_ID` РёР· СЃСЃС‹Р»РєРё. Р”Р»СЏ РєР°Р¶РґРѕРіРѕ СЃР°Р№С‚Р° СѓРєР°Р¶РёС‚Рµ СЃРІРѕР№ `WP_SITE_X_CATEGORY_ID`.
