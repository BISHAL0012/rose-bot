"""Locks: /lock <type> | /unlock <type> | /locks | /locktypes.

Locked message types are auto-deleted (admins are skipped).
"""

import re

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from utils import check_admin, is_user_admin, safe_delete, clean_reply

LOCK_TYPES = [
    "sticker", "gif", "media", "photo", "video", "document", "audio",
    "voice", "videonote", "url", "bots", "forward", "contact", "location",
    "poll", "game", "rtl", "button", "inline", "command", "all",
]

_RTL_RE = re.compile(r"[\u0590-\u08FF\u200F\u202B]")
_URL_RE = re.compile(r"https?://|t\.me/|www\.|@[A-Za-z0-9_]{5,32}\b", re.IGNORECASE)
_URL_ENTITY_TYPES = {"url", "text_link", "mention"}
# @SomeBot mentions and /command@SomeBot (other bots' links/commands)
_BOT_MENTION_RE = re.compile(r"@[A-Za-z0-9_]{4,31}bot\b", re.IGNORECASE)
_BOT_CMD_RE = re.compile(r"/[A-Za-z0-9_]+@[A-Za-z0-9_]{5,32}\b")
# leading /command (fallback when Telegram didn't tag a bot_command entity)
_CMD_RE = re.compile(r"^/[A-Za-z0-9_]+(?:@[A-Za-z0-9_]{5,32})?\b")


def _violates(msg, lock: str) -> bool:
    """True if the message violates the given lock type."""
    if lock == "sticker":
        return bool(msg.sticker)
    if lock == "gif":
        return bool(msg.animation)
    if lock == "media":
        return bool(msg.photo or msg.video or msg.document or msg.audio
                    or msg.voice or msg.video_note or msg.animation)
    if lock == "photo":
        return bool(msg.photo)
    if lock == "video":
        return bool(msg.video)
    if lock == "document":
        return bool(msg.document)
    if lock == "audio":
        return bool(msg.audio)
    if lock == "voice":
        return bool(msg.voice)
    if lock == "videonote":
        return bool(msg.video_note)
    if lock == "url":
        text = (msg.text or "") + (msg.caption or "")
        if _URL_RE.search(text):
            return True
        # formatted links / @mentions Telegram marks as entities
        for ent in list(msg.entities or []) + list(msg.caption_entities or []):
            if ent.type in _URL_ENTITY_TYPES:
                return True
        return False
    if lock == "bots":
        text = (msg.text or "") + (msg.caption or "")
        if _BOT_MENTION_RE.search(text) or _BOT_CMD_RE.search(text):
            return True
        # @bot mentions Telegram marks as mention entities
        for ent in list(msg.entities or []) + list(msg.caption_entities or []):
            if ent.type == "mention":
                mention = text[ent.offset:ent.offset + ent.length]
                if mention.lower().endswith("bot"):
                    return True
        # messages sent via another bot (inline)
        if msg.via_bot is not None:
            return True
        return False
    if lock == "forward":
        return bool(msg.forward_origin or msg.forward_date)
    if lock == "contact":
        return bool(msg.contact)
    if lock == "location":
        return bool(msg.location or msg.venue)
    if lock == "poll":
        return bool(msg.poll)
    if lock == "game":
        return bool(msg.game)
    if lock == "rtl":
        text = (msg.text or "") + (msg.caption or "")
        return bool(text) and bool(_RTL_RE.search(text[:50]))
    if lock == "button":
        return bool(msg.reply_markup and msg.reply_markup.inline_keyboard)
    if lock == "inline":
        return msg.via_bot is not None
    if lock == "command":
        # bot commands (/start, /start@OtherBot...) — Telegram marks them
        # as bot_command entities; also catch a leading /word fallback
        for ent in list(msg.entities or []) + list(msg.caption_entities or []):
            if ent.type == "bot_command":
                return True
        text = (msg.text or "") + (msg.caption or "")
        return bool(_CMD_RE.match(text.strip()))
    if lock == "all":
        return not (msg.text or msg.caption) or bool(
            msg.photo or msg.video or msg.document or msg.audio or msg.voice
            or msg.video_note or msg.animation or msg.sticker or msg.poll or msg.game)
    return False


async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args or context.args[0].lower() not in LOCK_TYPES:
        return await update.effective_message.reply_text(
            "ব্যবহার: /lock <type>\nটাইপ দেখতে: /locktypes")
    db.set_lock(update.effective_chat.id, context.args[0].lower(), True)
    await update.effective_message.reply_text(f"🔒 {context.args[0].lower()} লক করা হয়েছে।")


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args or context.args[0].lower() not in LOCK_TYPES:
        return await update.effective_message.reply_text(
            "ব্যবহার: /unlock <type>\nটাইপ দেখতে: /locktypes")
    db.set_lock(update.effective_chat.id, context.args[0].lower(), False)
    await update.effective_message.reply_text(f"🔓 {context.args[0].lower()} আনলক করা হয়েছে।")


async def locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = db.list_locks(update.effective_chat.id)
    lines = [f"{'🔒' if t in active else '🔓'} {t}" for t in LOCK_TYPES]
    await update.effective_message.reply_text("🔐 Locks:\n" + "\n".join(lines))


async def locktypes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🔐 Lock types:\n• " + "\n• ".join(LOCK_TYPES))


async def lock_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    if await is_user_admin(chat, msg.from_user.id):
        return
    for lock in db.list_locks(chat.id):
        if _violates(msg, lock):
            await safe_delete(msg)
            break


def register(app):
    for cmd, fn in [
        ("lock", lock), ("unlock", unlock), ("locks", locks), ("locktypes", locktypes),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, lock_watcher), group=1)
