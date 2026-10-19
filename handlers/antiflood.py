"""Anti-flood: /setflood <n> | /flood | /setfloodmode <ban|kick|mute|warn>.

Tracks per-user message timestamps in a 10-second sliding window.
Admins are exempt. Message timestamps live only in memory (ephemeral);
the limit and mode persist in SQLite.
"""

import time
from collections import defaultdict, deque

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from handlers.admin import PUNISH
from utils import check_admin, is_user_admin, clean_reply

WINDOW = 10  # seconds
_flood_tracker: dict = defaultdict(lambda: defaultdict(deque))
VALID_MODES = ("ban", "kick", "mute", "warn")


async def setflood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        cur = db.get_flood_limit(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান flood লিমিট: {'off' if cur == 0 else cur} (১০ সেকেন্ডে)\n"
            "ব্যবহার: /setflood <সংখ্যা>  (0 = বন্ধ)")
    db.set_flood_limit(chat_id, int(context.args[0]))
    await update.effective_message.reply_text(
        f"✅ Flood লিমিট: {context.args[0]} (0 = বন্ধ)")


async def flood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    limit = db.get_flood_limit(chat_id)
    mode = db.get_flood_mode(chat_id)
    await update.effective_message.reply_text(
        f"🌊 Flood: {'off' if limit == 0 else f'{limit} মেসেজ / ১০ সেকেন্ড'}\n"
        f"মোড: {mode}")


async def setfloodmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in VALID_MODES:
        return await update.effective_message.reply_text(
            f"বর্তমান: {db.get_flood_mode(chat_id)}\nব্যবহার: /setfloodmode <ban|kick|mute|warn>")
    db.set_flood_mode(chat_id, context.args[0].lower())
    await update.effective_message.reply_text(f"✅ Flood মোড: {context.args[0].lower()}")


async def flood_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user or not msg.text or msg.text.startswith("/"):
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    chat_id = chat.id
    limit = db.get_flood_limit(chat_id)
    if limit <= 0:
        return
    if await is_user_admin(chat, msg.from_user.id):
        return

    now = time.time()
    dq = _flood_tracker[chat_id][msg.from_user.id]
    dq.append(now)
    while dq and now - dq[0] > WINDOW:
        dq.popleft()
    if len(dq) > limit:
        dq.clear()
        mode = db.get_flood_mode(chat_id)
        try:
            await PUNISH[mode](chat, msg.from_user.id)
            await msg.reply_text(
                f"🌊 Flood করায় <a href='tg://user?id={msg.from_user.id}'>"
                f"{msg.from_user.first_name}</a> কে {mode} করা হয়েছে।",
                parse_mode="HTML")
        except Exception:
            pass


def register(app):
    for cmd, fn in [
        ("setflood", setflood), ("flood", flood), ("setfloodmode", setfloodmode),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, flood_watcher), group=2)
