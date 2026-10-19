"""Tagall: mention recent active members in batches.

/tagall <optional text>  - tag latest ~50 active members, 5 per message
"""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

import database as db
from utils import check_admin, command_text, html_escape, clean_reply

PER_BATCH = 5
MAX_USERS = 50


def batch_mentions(users, per_batch: int = PER_BATCH):
    """Pure: split [(user_id, name)] into mention-string batches."""
    batches = []
    for i in range(0, len(users), per_batch):
        chunk = users[i:i + per_batch]
        parts = []
        for uid, name in chunk:
            label = html_escape((name or "user").strip() or "user")
            parts.append(f'<a href="tg://user?id={uid}">{label}</a>')
        batches.append(" ".join(parts))
    return batches


async def tagall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    me_id = context.bot.id

    users = [(r["user_id"], r["name"]) for r in db.recent_members(chat_id, MAX_USERS)
             if r["user_id"] != me_id]
    if not users:
        return await update.effective_message.reply_text(
            "❌ ট্যাগ করার মতো মেম্বার পাওয়া যায়নি।")

    extra = command_text(update)
    batches = batch_mentions(users)
    first = True
    for b in batches:
        text = (f"📢 {html_escape(extra)}\n\n{b}" if first and extra else f"📢 {b}")
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        first = False


def register(app):
    app.add_handler(CommandHandler("tagall", tagall))
