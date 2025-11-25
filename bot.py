# bot.py
import os
import logging
import asyncio
import threading
import concurrent.futures
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from html import unescape
from typing import List, Dict, Set

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
                auth=(user, pwd),
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
        raise RuntimeError("Не заданы площадки для публикации. Заполните WP_SITE_* и/или TELEGRAM_TARGET_CHANNEL_ID.")
    return targets


WORDPRESS_SITES = load_wordpress_sites()
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
        inner = match.group(1).strip()
        return f"• {inner}\n"

    text = re.sub(r"<li[^>]*>(.*?)</li>", replace_li, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?(ul|ol)[^>]*>", "", text, flags=re.IGNORECASE)
    allowed = {"b", "i", "u", "a", "code", "pre"}

    def strip_tag(match: re.Match[str]) -> str:
        raw = match.group(0)
        name = match.group(1).lower()
        if name in allowed:
            return raw
        if name.startswith("/"):
            name = name[1:]
            if name in allowed:
                return raw
        return ""

    text = re.sub(r"</?([a-zA-Z0-9]+)[^>]*>", strip_tag, text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


# === Глобальные переменные ===
telegram_app = None
telegram_loop: asyncio.AbstractEventLoop | None = None
telegram_ready = threading.Event()
_app_lock = threading.Lock()

# === Публикации ===
def publish_to_wordpress_site(site: WordPressSite, draft: NewsDraft) -> tuple[bool, str]:
    try:
        media_url = f"{site.url}/wp-json/wp/v2/media"
        files = {"file": ("news.jpg", draft.photo_bytes, "image/jpeg")}
        media_res = requests.post(media_url, auth=site.auth, files=files, timeout=30)
        if media_res.status_code != 201:
            return False, f"❌ {site.name}: ошибка загрузки фото ({media_res.status_code})"
        media_id = media_res.json().get("id")
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
        post_res = requests.post(posts_url, auth=site.auth, json=post_payload, timeout=30)
        if post_res.status_code == 201:
            post_link = post_res.json().get("link", "Ссылка недоступна")
            return True, f"✅ {site.name}: опубликовано ({post_link})"
        return False, f"❌ {site.name}: ошибка публикации ({post_res.status_code})"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка публикации на %s: %s", site.name, exc)
        return False, f"⚠️ {site.name}: исключение {exc}"


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
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка публикации в Telegram: %s", exc)
        return False, f"⚠️ Telegram: {exc}"

# === Хендлеры Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_id = int(os.getenv("ALLOWED_USER_ID_1", "0")) or int(os.getenv("ALLOWED_USER_ID_2", "0")) or int(os.getenv("ALLOWED_USER_ID_3", "0"))
    if user_id != allowed_id:
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
    await update.message.reply_text(
        "🗓 Укажите дату публикации для WordPress сайтов в формате HH:MM MM.DD.YYYY или напишите «сейчас»."
    )
    return SCHEDULE


async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or text.lower() in {"сейчас", "now"}:
        context.user_data['publish_at'] = None
    else:
        try:
            publish_at = datetime.strptime(text, "%H:%M %m.%d.%Y")
            context.user_data['publish_at'] = publish_at
        except ValueError:
            await update.message.reply_text("Не получилось распознать дату. Используйте формат HH:MM MM.DD.YYYY.")
            return SCHEDULE
    await update.message.reply_text("🖼 Отправьте изображение (как фото, не как файл!):")
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
    message = update.effective_message
    selected: Set[str] = context.user_data.get('selected_targets', set())
    markup = build_targets_markup(selected)
    await message.reply_text(
        "Выберите площадки для публикации (можно несколько).",
        reply_markup=markup,
    )


def build_targets_markup(selected: Set[str]) -> InlineKeyboardMarkup:
    rows = []
    for target in PUBLICATION_TARGETS:
        prefix = "✅" if target.target_id in selected else "⬜️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {target.label}",
                    callback_data=f"toggle:{target.target_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("Опубликовать", callback_data="publish:go"),
            InlineKeyboardButton("Отмена", callback_data="publish:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def toggle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = query.data.split(":", 1)[1]
    selected: Set[str] = context.user_data.get('selected_targets', set())
    if target_id in selected:
        selected.remove(target_id)
    else:
        if target_id not in TARGETS_BY_ID:
            await query.answer("Неизвестная площадка.", show_alert=True)
            return TARGETS
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
            results.append(f"⚠️ Неизвестная площадка ({target_id}) пропущена.")
            continue
        if target.kind is TargetKind.WORDPRESS and target.site:
            success, detail = await asyncio.to_thread(publish_to_wordpress_site, target.site, draft)
        elif target.kind is TargetKind.TELEGRAM:
            success, detail = await publish_to_telegram_channel(draft, context.bot)
        else:
            success = False
            detail = f"⚠️ {target.label}: тип не поддерживается."
        results.append(detail)

    context.user_data.clear()
    header = "Результаты публикации:"
    await query.edit_message_text("\n".join([header, *results]), disable_web_page_preview=True)
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

# === Инициализация Telegram-приложения ===
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
    """
    Создаёт приложение Telegram в отдельном event loop и держит его активным.
    Flask-запросы затем прокидывают апдейты в этот loop через run_coroutine_threadsafe.
    """
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
        raise RuntimeError("Event loop Telegram приложения ещё не готов.")
    future = asyncio.run_coroutine_threadsafe(app_instance.process_update(update), telegram_loop)
    try:
        future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError("Превышено время обработки апдейта Telegram.")

# === Flask-приложение ===
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
        logger.error(f"Webhook error: {e}")
        return "Error", 500

# === Установка webhook при старте (вызывается вручную) ===
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
            logger.info(f"Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}")

# Запуск установки webhook при импорте (в безопасном потоке)
threading.Thread(target=set_webhook_if_needed, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)