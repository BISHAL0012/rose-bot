"""Zombies: track group members, find & clean deleted accounts.

/zombies        - scan tracked members, list deleted accounts
/zombies clean  - ban all found zombies

A lightweight watcher (group=8) records every message sender so scans
don't depend on admin-only member lists.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from utils import check_admin, clean_reply


def is_zombie(member) -> bool:
    """Pure check: a get_chat_member result that belongs to a deleted account."""
    try:
        user = member.user
    except AttributeError:
        return False
    return (user.first_name or "") == "Deleted Account"


def is_zombie_error(exc: Exception) -> bool:
    """True when get_chat_member failed because the user is gone."""
    msg = str(exc).lower()
    return "user not found" in msg or "member not found" in msg


# ------------------------------------------------------------ member tracker
async def track_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs on every group message (group=8); records the sender."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not msg.from_user or chat.type == "private":
        return
    user = msg.from_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    db.record_member(chat.id, user.id, name)


# ------------------------------------------------------------------ commands
async def zombies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    clean = bool(context.args and context.args[0].lower() == "clean")

    members = db.list_members(chat_id)
    if not members:
        return await update.effective_message.reply_text(
            "❌ এখনো কোনো মেম্বার ট্র্যাক হয়নি। কিছু মেসেজ আসার পর আবার চেষ্টা করুন।")

    status_msg = await update.effective_message.reply_text(
        f"🔍 {len(members)} জন স্ক্যান করা হচ্ছে…")
    found = []
    for row in members:
        uid = row["user_id"]
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
        except Exception as e:
            if is_zombie_error(e):
                found.append(uid)
            continue
        if member.status in ("left", "kicked"):
            continue
        if is_zombie(member):
            found.append(uid)

    if not found:
        return await status_msg.edit_text("✅ কোনো zombie (deleted account) পাওয়া যায়নি!")

    lines = [f"🧟 <b>{len(found)}টি zombie পাওয়া গেছে:</b>"]
    for uid in found[:50]:
        lines.append(f'• <a href="tg://user?id={uid}">deleted account</a> (<code>{uid}</code>)')
    if len(found) > 50:
        lines.append(f"…আরও {len(found) - 50}টি")

    if clean:
        banned = 0
        for uid in found:
            try:
                await context.bot.ban_chat_member(chat_id, uid)
                banned += 1
            except Exception:
                pass
        lines.append(f"\n🧹 <b>{banned}টি zombie clean করা হয়েছে।</b>")

    await status_msg.edit_text("\n".join(lines), parse_mode="HTML")


def register(app):
    app.add_handler(CommandHandler("zombies", zombies))
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, track_member),
        group=8,
    )
