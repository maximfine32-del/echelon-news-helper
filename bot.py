# bot.py
import os
import logging
import threading
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
import requests
from flask import Flask, request, jsonify

# === Настройка логирования ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Константы состояний ===
TITLE, EXCERPT, CONTENT, PHOTO = range(4)

# === Глобальные переменные для инициализации ===
telegram_app = None
_webhook_initialized = False
_init_lock = threading.Lock()

# === Функция публикации на WordPress ===
def publish_to_wordpress(title, excerpt, content, photo_file, sites):
    results = []
    for site in sites:
        try:
            # 1. Загружаем изображение
            auth = site['auth']
            media_url = f"{site['url']}/wp-json/wp/v2/media"
            files = {'file': ('news.jpg', photo_file, 'image/jpeg')}
            media_res = requests.post(
                media_url,
                auth=auth,
                files=files,
                headers={'Content-Disposition': 'attachment; filename=news.jpg'}
            )
            if media_res.status_code != 201:
                results.append(f"❌ Ошибка загрузки фото на {site['url']}: {media_res.status_code}")
                continue
            media_id = media_res.json().get('id')

            # 2. Публикуем запись
            post_data = {
                'title': title,
                'excerpt': excerpt,
                'content': content,
                'status': 'publish',
                'featured_media': media_id
            }
            post_res = requests.post(
                f"{site['url']}/wp-json/wp/v2/posts",
                auth=auth,
                json=post_data
            )
            if post_res.status_code == 201:
                post_link = post_res.json().get('link', 'Ссылка недоступна')
                results.append(f"✅ {post_link}")
            else:
                results.append(f"❌ Ошибка публикации на {site['url']}: {post_res.status_code}")
        except Exception as e:
            results.append(f"⚠️ Исключение на {site['url']}: {str(e)}")
    return results

# === Хендлеры Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_id = int(os.getenv("ALLOWED_USER_ID", "0"))
    if user_id != allowed_id:
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return ConversationHandler.END
    await update.message.reply_text("📰 Отправьте заголовок новости:")
    return TITLE

async def title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("🔖 Отправьте анонс (краткое описание):")
    return EXCERPT

async def excerpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['excerpt'] = update.message.text
    await update.message.reply_text("📝 Отправьте полный текст новости:")
    return CONTENT

async def content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['content'] = update.message.text
    await update.message.reply_text("🖼 Отправьте изображение (как фото, не как файл!):")
    return PHOTO

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    title = context.user_data['title']
    excerpt = context.user_data['excerpt']
    content = context.user_data['content']

    # Формируем список сайтов
    sites = []
    for i in range(1, 4):
        url = os.getenv(f"WP_SITE_{i}_URL")
        user = os.getenv(f"WP_SITE_{i}_USER")
        pwd = os.getenv(f"WP_SITE_{i}_PASS")
        if url and user and pwd:
            sites.append({'url': url, 'auth': (user, pwd)})

    if not sites:
        await update.message.reply_text("⚠️ Не настроены WordPress-сайты.")
        return ConversationHandler.END

    await update.message.reply_text("📤 Публикую на всех сайтах...")

    try:
        results = publish_to_wordpress(title, excerpt, content, bytes(photo_bytes), sites)
        for res in results:
            await update.message.reply_text(res)
    except Exception as e:
        logger.error(f"Ошибка при публикации: {e}")
        await update.message.reply_text(f"❌ Критическая ошибка: {str(e)}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Публикация отменена.")
    return ConversationHandler.END

# === Инициализация Telegram-приложения и webhook ===
def init_telegram_app():
    global telegram_app
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан")

    telegram_app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title)],
            EXCERPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, excerpt)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content)],
            PHOTO: [MessageHandler(filters.PHOTO, photo)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    telegram_app.add_handler(conv_handler)
    telegram_app.initialize()

def set_webhook():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not token or not render_url:
        logger.warning("TELEGRAM_BOT_TOKEN или RENDER_EXTERNAL_URL не заданы. Webhook не установлен.")
        return

    webhook_url = f"https://{render_url}/webhook/{token}"
    bot = Bot(token=token)
    try:
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook успешно установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"Не удалось установить webhook: {e}")

# === Flask-приложение ===
app = Flask(__name__)

@app.before_request
def initialize_webhook_once():
    global _webhook_initialized
    if not _webhook_initialized:
        with _init_lock:
            if not _webhook_initialized:
                init_telegram_app()
                set_webhook()
                _webhook_initialized = True

@app.route("/webhook/<token>", methods=["POST"])
def telegram_webhook(token):
    if token != os.getenv("TELEGRAM_BOT_TOKEN"):
        return "Forbidden", 403
    if telegram_app is None:
        return "Application not ready", 503
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)