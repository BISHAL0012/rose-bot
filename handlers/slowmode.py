"""Bot-enforced slowmode (Telegram Bot API has no native setter).

/slowmode <seconds|off>  - 5..300s between messages per user (admins exempt)
"""

import time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from utils import check_admin, is_user_admin, safe_delete, clean_reply

MIN_S, MAX_S = 5, 300
_last: dict = {}  # (chat_id, user_id) -> timestamp


def should_delete(last_ts: float, now: float, limit: int) -> bool:
    """Pure: True if a message at `now` violates the slowmode limit."""
    if limit <= 0:
        return False
    return (now - last_ts) < limit


async def slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args:
        cur = db.get_slowmode(chat_id)
        return await update.effective_message.reply_text(
            f"🐢 Slowmode: {'off' if cur == 0 else f'{cur} সেকেন্ড'}\n"
            "ব্যবহার: /slowmode <seconds|off>  (৫–৩০০)")
    arg = context.args[0].lower()
    if arg in ("off", "no", "0"):
        db.set_slowmode(chat_id, 0)
        return await update.effective_message.reply_text("✅ Slowmode বন্ধ।")
    if not arg.isdigit() or not (MIN_S <= int(arg) <= MAX_S):
        return await update.effective_message.reply_text(
            "❌ ৫ থেকে ৩০০ সেকেন্ডের মধ্যে দিন, অথবা off।")
    db.set_slowmode(chat_id, int(arg))
    await update.effective_message.reply_text(
        f"✅ Slowmode চালু: প্রতি {arg} সেকেন্ডে ১টি মেসেজ।")


async def slowmode_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    text = msg.text or ""
    if text.startswith("/"):
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    limit = db.get_slowmode(chat.id)
    if limit <= 0:
        return
    if await is_user_admin(chat, msg.from_user.id):
        return
    now = time.time()
    key = (chat.id, msg.from_user.id)
    if should_delete(_last.get(key, 0), now, limit):
        await safe_delete(msg)
    else:
        _last[key] = now


def register(app):
    app.add_handler(CommandHandler("slowmode", slowmode))
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, slowmode_watcher),
        group=9,
    )
