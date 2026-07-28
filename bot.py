# bot.py
import os
import logging
import asyncio
import threading
import concurrent.futures
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from html import unescape
from typing import List, Dict, Set, Optional

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import requests
from flask import Flask, request, jsonify

# === Логирование ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Состояния диалога ===
TITLE, EXCERPT, CONTENT, SCHEDULE, PHOTO, TARGETS = range(6)

# === Конфигурация публикаций ===
TARGET_LABEL_OVERRIDES = {
    "wp:site1": 'Cайт АО "Эшелон Технологии"',
    "wp:site2": 'Сайт АО "НПО "Эшелон"',
    "wp:site3": 'Партнерский портал',
    "telegram:channel": 'Telegram-канал "Echelon Eyes"',
}

@dataclass(frozen=True)
class WordPressSite:
    slug: str
    name: str
    url: str
    auth: tuple[str, str]
    category_id: int

class TargetKind(Enum):
    WORDPRESS = auto()
    TELEGRAM = auto()

@dataclass(frozen=True)
class PublicationTarget:
    target_id: str
    label: str
    kind: TargetKind
    site: WordPressSite | None = None

@dataclass
class NewsDraft:
    title: str
    excerpt: str
    content: str
    photo_bytes: bytes
    publish_at: datetime | None

# === Cookie Authentication с обходом базовых WAF ===
_wp_sessions: Dict[str, tuple[requests.Session, str, datetime]] = {}

def login_to_wordpress(site: WordPressSite) -> tuple[requests.Session, str]:
    logger.info("🔐 Попытка входа в WordPress: %s (user: %s)", site.url, site.auth[0])
    
    session = requests.Session()
    # Максимально реалистичные заголовки браузера для обхода WAF
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': f'{site.url}/wp-login.php',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
    })
    
    login_url = f"{site.url}/wp-login.php"
    try:
        # Небольшая задержка, чтобы не триггерить rate-limit
        time.sleep(1.5)
        initial_res = session.get(login_url, timeout=15)
        logger.debug("Получена страница логина, статус: %d", initial_res.status_code)
    except Exception as e:
        raise RuntimeError(f"Не удалось получить страницу логина (возможна блокировка WAF): {e}")
    
    login_data = {
        'log': site.auth[0],
        'pwd': site.auth[1],
        'wp-submit': 'Войти',
        'redirect_to': f'{site.url}/wp-admin/',
        'testcookie': '1',
    }
    
    try:
        # Увеличиваем таймаут до 30 секунд на случай медленных проверок безопасности
        login_res = session.post(login_url, data=login_data, allow_redirects=True, timeout=30)
        logger.debug("Ответ после логина, статус: %d, URL: %s", login_res.status_code, login_res.url)
    except requests.exceptions.ReadTimeout:
        raise RuntimeError("Сервер не ответил на запрос входа (таймаут). Вероятно, запрос заблокирован WAF (Cloudflare/Wordfence) на уровне сети.")
    except Exception as e:
        raise RuntimeError(f"Ошибка при отправке формы логина: {e}")
    
    if 'wp-admin' not in login_res.url and 'wp-login.php' in login_res.url:
        raise RuntimeError(f"Логин не удался. Проверьте логин и обычный пароль (не Application Password) для {site.name}")
    
    has_auth_cookie = any('wordpress_logged_in' in cookie.name for cookie in session.cookies)
    if not has_auth_cookie:
        raise RuntimeError(f"Не получены cookies авторизации для {site.name}. Возможно, включена 2FA или блокировка по IP.")
    
    logger.info("✅ Успешный вход в WordPress: %s", site.name)
    nonce = get_nonce(session, site.url)
    return session, nonce

def get_nonce(session: requests.Session, site_url: str) -> str:
    try:
        admin_url = f"{site_url}/wp-admin/"
        time.sleep(1) # Задержка между запросами
        admin_res = session.get(admin_url, timeout=15)
        if admin_res.status_code == 200:
            nonce_match = re.search(r'"nonce"\s*:\s*"([^"]+)"', admin_res.text)
            if nonce_match:
                return nonce_match.group(1)
            nonce_match = re.search(r'wpApiSettings\s*=\s*\{.*?nonce\s*:\s*["\']([^"\']+)["\']', admin_res.text)
            if nonce_match:
                return nonce_match.group(1)
    except Exception as e:
        logger.debug("Не удалось получить nonce: %s", e)
    
    raise RuntimeError("Не удалось получить nonce. WordPress может блокировать доступ к админке.")

def get_wp_session(site: WordPressSite) -> tuple[requests.Session, str]:
    now = datetime.now()
    if site.slug in _wp_sessions:
        session, nonce, expires_at = _wp_sessions[site.slug]
        if now < expires_at:
            return session, nonce
        else:
            logger.info("Сессия для %s истекла, создаем новую", site.name)
            del _wp_sessions[site.slug]
    
    session, nonce = login_to_wordpress(site)
    expires_at = now + timedelta(hours=1)
    _wp_sessions[site.slug] = (session, nonce, expires_at)
    return session, nonce

def load_wordpress_sites() -> List[WordPressSite]:
    sites: List[WordPressSite] = []
    for idx in range(1, 4):
        url = os.getenv(f"WP_SITE_{idx}_URL")
        user = os.getenv(f"WP_SITE_{idx}_USER")
        pwd = os.getenv(f"WP_SITE_{idx}_PASS")
        category_raw = os.getenv(f"WP_SITE_{idx}_CATEGORY_ID")
        if not (url and user and pwd and category_raw):
            continue
        try:
            category_id = int(category_raw)
        except ValueError:
            logger.warning("WP_SITE_%s_CATEGORY_ID не число, сайт пропущен.", idx)
            continue
        name = os.getenv(f"WP_SITE_{idx}_NAME", f"Сайт {idx}")
        slug = os.getenv(f"WP_SITE_{idx}_SLUG", f"site{idx}")
        sites.append(
            WordPressSite(
                slug=slug,
                name=name,
                url=url.rstrip("/"),
                auth=(user, pwd), # Здесь должен быть ОБЫЧНЫЙ пароль WordPress
                category_id=category_id,
            )
        )
    return sites

def build_targets(sites: List[WordPressSite], telegram_channel: str | None) -> List[PublicationTarget]:
    targets: List[PublicationTarget] = []
    for site in sites:
        target_id = f"wp:{site.slug}"
        targets.append(
            PublicationTarget(
                target_id=target_id,
                label=TARGET_LABEL_OVERRIDES.get(target_id, f"WordPress · {site.name}"),
                kind=TargetKind.WORDPRESS,
                site=site,
            )
        )
    if telegram_channel:
        targets.append(
            PublicationTarget(
                target_id="telegram:channel",
                label=TARGET_LABEL_OVERRIDES.get("telegram:channel", "Telegram-канал"),
                kind=TargetKind.TELEGRAM,
            )
        )
    if not targets:
        raise RuntimeError("Не заданы площадки для публикации.")
    return targets

WORDPRESS_SITES = load_wordpress_sites()
logger.info("🌐 Загружено WordPress сайтов: %d", len(WORDPRESS_SITES))
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_TARGET_CHANNEL_ID")
PUBLICATION_TARGETS = build_targets(WORDPRESS_SITES, TELEGRAM_CHANNEL_ID)
TARGETS_BY_ID: Dict[str, PublicationTarget] = {target.target_id: target for target in PUBLICATION_TARGETS}

def html_to_telegram(html_text: str) -> str:
    if not html_text:
        return ""
    text = html_text.replace("<strong>", "<b>").replace("</strong>", "</b>")
    text = text.replace("<em>", "<i>").replace("</em>", "</i>")
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*p[^>]*>", "", text, flags=re.IGNORECASE)
    def replace_li(match: re.Match[str]) -> str:
        return f"• {match.group(1).strip()}\n"
    text = re.sub(r"<li[^>]*>(.*?)</li>", replace_li, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?(ul|ol)[^>]*>", "", text, flags=re.IGNORECASE)
    allowed = {"b", "i", "u", "a", "code", "pre"}
    def strip_tag(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if name in allowed or (name.startswith("/") and name[1:] in allowed):
            return match.group(0)
        return ""
    text = re.sub(r"</?([a-zA-Z0-9]+)[^>]*>", strip_tag, text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

telegram_app = None
telegram_loop: asyncio.AbstractEventLoop | None = None
telegram_ready = threading.Event()
_app_lock = threading.Lock()

def publish_to_wordpress_site(site: WordPressSite, draft: NewsDraft) -> tuple[bool, str]:
    try:
        logger.info("🚀 Начало публикации на сайт: %s", site.name)
        try:
            session, nonce = get_wp_session(site)
        except Exception as auth_error:
            logger.error("❌ Ошибка аутентификации: %s", auth_error)
            return False, f"❌ {site.name}: ошибка входа ({auth_error})"
        
        session.headers.update({'X-WP-Nonce': nonce, 'Referer': f'{site.url}/wp-admin/'})
        
        media_url = f"{site.url}/wp-json/wp/v2/media"
        files = {"file": ("news.jpg", draft.photo_bytes, "image/jpeg")}
        
        logger.info("📤 Загрузка медиа...")
        media_res = session.post(media_url, files=files, timeout=30)
        
        if media_res.status_code != 201:
            logger.error("❌ Ошибка загрузки медиа. Статус: %d, Ответ: %s", media_res.status_code, media_res.text[:300])
            return False, f"❌ {site.name}: ошибка загрузки фото ({media_res.status_code})"
            
        media_id = media_res.json().get("id")
        logger.info("✅ Медиа загружено, ID: %s", media_id)
        
        post_payload = {
            "title": draft.title,
            "excerpt": draft.excerpt,
            "content": draft.content,
            "status": "publish",
            "featured_media": media_id,
            "categories": [site.category_id],
        }
        if draft.publish_at:
            post_payload["date"] = draft.publish_at.strftime("%Y-%m-%dT%H:%M:%S")
        
        posts_url = f"{site.url}/wp-json/wp/v2/posts"
        logger.info("📤 Создание поста...")
        post_res = session.post(posts_url, json=post_payload, timeout=30)
        
        if post_res.status_code == 201:
            post_link = post_res.json().get("link", "Ссылка недоступна")
            return True, f"✅ {site.name}: опубликовано ({post_link})"
        
        logger.error("❌ Ошибка создания поста. Статус: %d, Ответ: %s", post_res.status_code, post_res.text[:300])
        return False, f"❌ {site.name}: ошибка публикации ({post_res.status_code})"
        
    except requests.exceptions.RequestException as req_exc:
        logger.error("⚠️ Сетевая ошибка: %s", req_exc)
        return False, f"⚠️ {site.name}: сетевая ошибка {req_exc}"
    except Exception as exc:
        logger.exception("️ Неожиданная ошибка: %s", exc)
        return False, f"️ {site.name}: исключение {exc}"

async def publish_to_telegram_channel(draft: NewsDraft, bot: Bot) -> tuple[bool, str]:
    if not TELEGRAM_CHANNEL_ID:
        return False, "Телеграм-канал не настроен."
    parts = [f"<b>{draft.title}</b>"]
    if draft.excerpt.strip():
        parts.append(draft.excerpt.strip())
    formatted_content = html_to_telegram(draft.content)
    if formatted_content:
        parts.append(formatted_content)
    caption = "\n\n".join(parts).strip()
    if len(caption) > 1024:
        caption = caption[:1019].rstrip() + "…"
    try:
        await bot.send_photo(
            chat_id=TELEGRAM_CHANNEL_ID,
            photo=draft.photo_bytes,
            caption=caption[:1024],
            parse_mode=ParseMode.HTML,
        )
        return True, "✅ Telegram: публикация отправлена."
    except Exception as exc:
        logger.exception("Ошибка публикации в Telegram: %s", exc)
        return False, f"️ Telegram: {exc}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_ids_str = os.getenv("ALLOWED_USER_IDS", "")
    try:
        allowed_ids = [int(x.strip()) for x in allowed_ids_str.split(",") if x.strip()]
    except ValueError:
        allowed_ids = []
    if user_id not in allowed_ids:
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return ConversationHandler.END
    await update.message.reply_text("📰 Отправьте заголовок новости:")
    return TITLE

async def title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("🔖 Отправьте анонс:")
    return EXCERPT

async def excerpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['excerpt'] = update.message.text
    await update.message.reply_text("📝 Отправьте полный текст:")
    return CONTENT

async def content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['content'] = update.message.text
    await update.message.reply_text("🗓 Укажите дату публикации (HH:MM DD.MM.YYYY) или «Сейчас».")
    return SCHEDULE

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or text.lower() in {"сейчас", "now"}:
        context.user_data['publish_at'] = None
    else:
        try:
            publish_at = datetime.strptime(text, "%H:%M %d.%m.%Y")
            context.user_data['publish_at'] = publish_at
        except ValueError:
            await update.message.reply_text("Не получилось распознать дату. Используйте формат HH:MM DD.MM.YYYY.")
            return SCHEDULE
    await update.message.reply_text("🖼 Отправьте изображение (как фото):")
    return PHOTO

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Нужно прислать изображение как фото.")
        return PHOTO
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    context.user_data['draft'] = NewsDraft(
        title=context.user_data['title'],
        excerpt=context.user_data['excerpt'],
        content=context.user_data['content'],
        photo_bytes=bytes(photo_bytes),
        publish_at=context.user_data.get('publish_at'),
    )
    context.user_data['selected_targets'] = set()
    await send_target_selection(update, context)
    return TARGETS

async def send_target_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected: Set[str] = context.user_data.get('selected_targets', set())
    await update.effective_message.reply_text("Выберите площадки:", reply_markup=build_targets_markup(selected))

def build_targets_markup(selected: Set[str]) -> InlineKeyboardMarkup:
    rows = []
    for target in PUBLICATION_TARGETS:
        prefix = "✅" if target.target_id in selected else "⬜️"
        rows.append([InlineKeyboardButton(f"{prefix} {target.label}", callback_data=f"toggle:{target.target_id}")])
    rows.append([
        InlineKeyboardButton("Опубликовать", callback_data="publish:go"),
        InlineKeyboardButton("Отмена", callback_data="publish:cancel"),
    ])
    return InlineKeyboardMarkup(rows)

async def toggle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = query.data.split(":", 1)[1]
    selected: Set[str] = context.user_data.get('selected_targets', set())
    if target_id in selected:
        selected.remove(target_id)
    else:
        selected.add(target_id)
    context.user_data['selected_targets'] = selected
    await query.edit_message_reply_markup(reply_markup=build_targets_markup(selected))
    return TARGETS

async def publish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected: Set[str] = context.user_data.get('selected_targets', set())
    if not selected:
        await query.answer("Выберите хотя бы одну площадку.", show_alert=True)
        return TARGETS
    draft: NewsDraft = context.user_data['draft']
    await query.answer("Публикуем...")
    await query.edit_message_text("Публикуем новость, подождите...")

    results = []
    for target_id in selected:
        target = TARGETS_BY_ID.get(target_id)
        if not target:
            results.append(f"⚠️ Неизвестная площадка ({target_id})")
            continue
        if target.kind is TargetKind.WORDPRESS and target.site:
            success, detail = await asyncio.to_thread(publish_to_wordpress_site, target.site, draft)
        elif target.kind is TargetKind.TELEGRAM:
            success, detail = await publish_to_telegram_channel(draft, context.bot)
        else:
            success, detail = False, f"⚠️ {target.label}: тип не поддерживается."
        results.append(detail)

    context.user_data.clear()
    await query.edit_message_text("Результаты:\n" + "\n".join(results), disable_web_page_preview=True)
    return ConversationHandler.END

async def cancel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Отменено.")
    await query.edit_message_text("Публикация отменена.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Отменено.")
    context.user_data.clear()
    return ConversationHandler.END

def _build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title)],
            EXCERPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, excerpt)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content)],
            SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule)],
            PHOTO: [MessageHandler(filters.PHOTO & ~filters.COMMAND, photo)],
            TARGETS: [
                CallbackQueryHandler(toggle_target, pattern=r"^toggle:"),
                CallbackQueryHandler(publish_handler, pattern=r"^publish:go$"),
                CallbackQueryHandler(cancel_selection, pattern=r"^publish:cancel$"),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

def _application_thread() -> None:
    global telegram_app, telegram_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан")

    application = Application.builder().token(token).build()
    application.add_handler(_build_conversation_handler())

    async def _startup():
        await application.initialize()
        await application.start()

    loop.run_until_complete(_startup())
    telegram_app = application
    telegram_loop = loop
    telegram_ready.set()
    logger.info("✅ Telegram приложение инициализировано")

    try:
        loop.run_forever()
    finally:
        async def _shutdown():
            await application.stop()
            await application.shutdown()
        loop.run_until_complete(_shutdown())
        loop.close()

def get_telegram_app():
    if telegram_app is None:
        with _app_lock:
            if telegram_app is None:
                thread = threading.Thread(target=_application_thread, daemon=True)
                thread.start()
        if not telegram_ready.wait(timeout=10):
            raise RuntimeError("Не удалось инициализировать Telegram application.")
    return telegram_app

def _process_update(update: Update) -> None:
    app_instance = get_telegram_app()
    if telegram_loop is None:
        raise RuntimeError("Event loop не готов.")
    future = asyncio.run_coroutine_threadsafe(app_instance.process_update(update), telegram_loop)
    try:
        future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError("Превышено время обработки апдейта.")

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != os.getenv("TELEGRAM_BOT_TOKEN"):
        return "Forbidden", 403
    try:
        app_instance = get_telegram_app()
        update = Update.de_json(request.get_json(force=True), app_instance.bot)
        _process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return "Error", 500

def set_webhook_if_needed():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if token and render_url:
        clean_base = render_url.rstrip("/")
        if not clean_base.startswith("http://") and not clean_base.startswith("https://"):
            clean_base = f"https://{clean_base}"
        webhook_url = f"{clean_base}/webhook/{token}"
        bot = Bot(token=token)
        try:
            asyncio.run(bot.set_webhook(url=webhook_url))
            logger.info(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}", exc_info=True)

threading.Thread(target=set_webhook_if_needed, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
