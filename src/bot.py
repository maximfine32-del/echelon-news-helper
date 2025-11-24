from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import List, Sequence, Set

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig, WordPressSiteConfig, get_cached_config
from .wordpress_client import WordPressClient

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s [%(funcName)s]: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class FormState(Enum):
    TITLE = auto()
    EXCERPT = auto()
    CONTENT = auto()
    PHOTO = auto()
    TARGETS = auto()


class TargetKind(Enum):
    WORDPRESS = "wordpress"
    TELEGRAM = "telegram"


@dataclass(frozen=True)
class PublicationTarget:
    target_id: str
    label: str
    kind: TargetKind
    site_slug: str | None = None


@dataclass
class NewsDraft:
    title: str
    excerpt: str
    content: str
    image_bytes: bytes
    image_filename: str


@dataclass
class PublicationResult:
    target_label: str
    success: bool
    detail: str


class PublisherService:
    """Coordinates publishing to the requested destinations."""

    def __init__(self, config: AppConfig, targets: Sequence[PublicationTarget]):
        self.config = config
        self.targets = {target.target_id: target for target in targets}

    async def publish(self, draft: NewsDraft, target_ids: Sequence[str], bot) -> List[PublicationResult]:
        results: List[PublicationResult] = []
        for target_id in target_ids:
            target = self.targets[target_id]
            logger.info("Начинаю публикацию на %s (%s)", target.label, target.kind.value)
            if target.kind is TargetKind.WORDPRESS and target.site_slug:
                results.append(await self._publish_wordpress(target, draft))
            elif target.kind is TargetKind.TELEGRAM:
                results.append(await self._publish_telegram(target, draft, bot))
            else:
                results.append(
                    PublicationResult(
                        target_label=target.label,
                        success=False,
                        detail="Тип публикации не поддерживается.",
                    )
                )
        return results

    async def _publish_wordpress(self, target: PublicationTarget, draft: NewsDraft) -> PublicationResult:
        site_config = self.config.sites_by_slug[target.site_slug]  # type: ignore[index]
        try:
            logger.info(
                "WordPress публикация: slug=%s title=%s category=%s",
                site_config.slug,
                draft.title,
                site_config.news_category_id,
            )
            async with WordPressClient(site_config) as client:
                media_id = await client.upload_media(draft.image_filename, draft.image_bytes)
                logger.info("Изображение загружено, media_id=%s", media_id)
                post = await client.create_post(
                    title=draft.title,
                    excerpt=draft.excerpt,
                    content=draft.content,
                    featured_media=media_id,
                )
            logger.info("WordPress пост создан: %s", post.get("link"))
            return PublicationResult(
                target_label=target.label,
                success=True,
                detail=f"Опубликовано: {post.get('link', 'без ссылки')}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("WordPress publish failed for %s: %s", target.label, exc)
            return PublicationResult(target_label=target.label, success=False, detail=str(exc))

    async def _publish_telegram(self, target: PublicationTarget, draft: NewsDraft, bot) -> PublicationResult:
        try:
            logger.info(
                "Отправляю новость в Telegram канал %s. Заголовок: %s",
                self.config.telegram_channel.channel_id,
                draft.title,
            )
            caption = f"<b>{draft.title}</b>\n\n{draft.excerpt}"
            await bot.send_photo(
                chat_id=self.config.telegram_channel.channel_id,
                photo=draft.image_bytes,
                caption=caption[:1024],
                parse_mode=ParseMode.HTML,
            )
            if draft.content.strip():
                await bot.send_message(
                    chat_id=self.config.telegram_channel.channel_id,
                    text=draft.content,
                )
            logger.info("Telegram публикация завершена успешно.")
            return PublicationResult(
                target_label=target.label,
                success=True,
                detail="Новость отправлена в канал.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram publish failed: %s", exc)
            return PublicationResult(target_label=target.label, success=False, detail=str(exc))


def build_targets(config: AppConfig) -> List[PublicationTarget]:
    targets: List[PublicationTarget] = []
    for site in config.wordpress_sites:
        targets.append(
            PublicationTarget(
                target_id=f"wp:{site.slug}",
                label=f"WordPress · {site.name}",
                kind=TargetKind.WORDPRESS,
                site_slug=site.slug,
            )
        )

    if config.telegram_channel.publish_enabled:
        targets.append(
            PublicationTarget(
                target_id="telegram:channel",
                label="Telegram канал",
                kind=TargetKind.TELEGRAM,
            )
        )

    if not targets:
        raise RuntimeError("Не заданы площадки для публикации.")

    return targets


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    config: AppConfig = context.application.bot_data["config"]
    chat_id = update.effective_chat.id if update.effective_chat else None
    if config.allowed_chat_ids and chat_id not in config.allowed_chat_ids:
        await update.effective_message.reply_text("У вас нет доступа к этому боту.")
        return ConversationHandler.END

    context.user_data.clear()
    await update.effective_message.reply_text(
        "Привет! Отправьте заголовок новости.",
    )
    return FormState.TITLE


async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Теперь пришлите короткий отрывок новости.")
    return FormState.EXCERPT


async def handle_excerpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    context.user_data["excerpt"] = update.message.text.strip()
    await update.message.reply_text("Отправьте полный текст новости.")
    return FormState.CONTENT


async def handle_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    context.user_data["content"] = update.message.text.strip()
    await update.message.reply_text("Пришлите картинку для новости (фото).")
    return FormState.PHOTO


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    if not update.message.photo:
        await update.message.reply_text("Нужно отправить именно фото.")
        return FormState.PHOTO

    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    file_path = Path(file.file_path or "news.jpg")
    filename = file_path.name if file_path.suffix else f"{file_path.stem}.jpg"
    context.user_data["image_bytes"] = bytes(data)
    context.user_data["image_filename"] = filename
    context.user_data["selected_targets"] = set()

    await send_target_selection(update.effective_message, context)
    return FormState.TARGETS


async def send_target_selection(message: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
    targets: Sequence[PublicationTarget] = context.application.bot_data["targets"]
    markup = build_targets_markup(targets, set())
    await message.reply_text(
        "Выберите площадки для публикации (можно несколько).",
        reply_markup=markup,
    )


def build_targets_markup(targets: Sequence[PublicationTarget], selected: Set[str]) -> InlineKeyboardMarkup:
    rows = []
    for target in targets:
        indicator = "✅" if target.target_id in selected else "⬜️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{indicator} {target.label}",
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


async def toggle_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FormState:
    query = update.callback_query
    await query.answer()
    target_id = query.data.split(":", 1)[1]
    selected: Set[str] = context.user_data.get("selected_targets", set())
    if target_id in selected:
        selected.remove(target_id)
    else:
        selected.add(target_id)
    context.user_data["selected_targets"] = selected

    targets: Sequence[PublicationTarget] = context.application.bot_data["targets"]
    await query.edit_message_reply_markup(reply_markup=build_targets_markup(targets, selected))
    return FormState.TARGETS


async def publish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    selected: Set[str] = context.user_data.get("selected_targets", set())
    if not selected:
        await query.answer("Выберите хотя бы одну площадку.", show_alert=True)
        return FormState.TARGETS

    logger.info("Публикация запущена пользователем %s. targets=%s", query.from_user.id, selected)

    await query.answer("Публикую...")
    await query.edit_message_text("Публикуем новость, подождите...")

    draft = NewsDraft(
        title=context.user_data["title"],
        excerpt=context.user_data["excerpt"],
        content=context.user_data["content"],
        image_bytes=context.user_data["image_bytes"],
        image_filename=context.user_data["image_filename"],
    )

    publisher: PublisherService = context.application.bot_data["publisher"]
    results = await publisher.publish(draft, list(selected), context.bot)
    logger.info("Публикация завершена. Results=%s", results)

    lines = ["Результаты публикации:"]
    for result in results:
        icon = "✅" if result.success else "⚠️"
        lines.append(f"{icon} {result.target_label} — {result.detail}")

    await query.edit_message_text("\n".join(lines), disable_web_page_preview=True)
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Публикация отменена. Наберите /start, чтобы начать заново.")
    context.user_data.clear()
    return ConversationHandler.END


def build_application(config: AppConfig) -> Application:
    targets = build_targets(config)
    application = (
        Application.builder()
        .token(config.bot_token)
        .rate_limiter(AIORateLimiter())
        .post_init(register_shared_objects(config, targets))
        .build()
    )

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FormState.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
            FormState.EXCERPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_excerpt)],
            FormState.CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_content)],
            FormState.PHOTO: [MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo)],
            FormState.TARGETS: [
                CallbackQueryHandler(toggle_target, pattern=r"^toggle:"),
                CallbackQueryHandler(publish_handler, pattern=r"^publish:go$"),
                CallbackQueryHandler(cancel_handler, pattern=r"^publish:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        name="news_publisher",
        persistent=False,
    )
    application.add_handler(conversation)
    return application


def register_shared_objects(config: AppConfig, targets: Sequence[PublicationTarget]):
    async def _initializer(application: Application) -> None:
        application.bot_data["config"] = config
        application.bot_data["targets"] = targets
        application.bot_data["publisher"] = PublisherService(config, targets)

    return _initializer


def main() -> None:
    config = get_cached_config()
    application = build_application(config)
    application.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()

