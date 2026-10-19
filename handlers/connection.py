"""PM <-> group connection (Rose-style /connect).

/connect in a group  -> links your PM to that group.
/connect in PM       -> pick a group from buttons.
/disconnect          -> remove the link.

While linked, any command you send to the bot in PM is executed
as if you sent it in the connected group (admin rights re-checked).
/connect, /disconnect, /start and /help always stay local to PM.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database as db
from utils import issuer_is_admin

# Commands that are never routed to the connected group.
_LOCAL_CMDS = {"/connect", "/disconnect", "/start", "/help"}

# chat ids already recorded in known_chats (avoids a DB write per message)
_seen_chats: set = set()


async def _remember_chat(chat) -> None:
    if not chat or chat.type == "private" or chat.id in _seen_chats:
        return
    _seen_chats.add(chat.id)
    db.remember_chat(chat.id, chat.title or "", chat.type)


async def record_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remember every group/supergroup the bot sees (runs first, group=-2)."""
    await _remember_chat(update.effective_chat)


# ------------------------------------------------------------------ connect
async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        # ---- in-group: link this user to this group
        if not await issuer_is_admin(update, context):
            return await msg.reply_text("❌ শুধু গ্রুপ অ্যাডমিনরা কানেক্ট করতে পারেন।")
        await _remember_chat(chat)
        db.set_connection(user.id, chat.id)
        return await msg.reply_text(
            f"🔗 <b>{chat.title}</b> গ্রুপে কানেক্টেড!\n"
            "এখন বটের PM-এ কমান্ড দিলে এই গ্রুপে কাজ করবে।\n"
            "সংযোগ ছাড়তে: /disconnect",
            parse_mode=ParseMode.HTML,
        )

    # ---- in PM: choose from groups where the user is admin
    current = db.get_connection(user.id)
    buttons = []
    for row in db.list_known_chats():
        try:
            m = await context.bot.get_chat_member(row["chat_id"], user.id)
        except Exception:
            continue
        if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            continue
        label = ("✅ " if current == row["chat_id"] else "") + (
            row["title"] or str(row["chat_id"])
        )
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"connect:{row['chat_id']}")]
        )

    text = (
        "🔗 <b>Connect</b> — গ্রুপ বেছে নিন:\n"
        "PM থেকে কমান্ড দিলে ওই গ্রুপে কাজ করবে।"
    )
    if current:
        text += "\n\nবর্তমান সংযোগ: <code>{}</code> (/disconnect দিয়ে ছাড়ুন)".format(current)
    if not buttons:
        return await msg.reply_text(
            text
            + "\n\n❌ কোনো গ্রুপ পাওয়া যায়নি। বটকে গ্রুপে অ্যাড করে অ্যাডমিন করুন, "
              "তারপর ওই গ্রুপে /connect দিন।",
            parse_mode=ParseMode.HTML,
        )
    await msg.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def disconnect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.get_connection(user.id):
        db.del_connection(user.id)
        await update.effective_message.reply_text("🔌 সংযোগ বিচ্ছিন্ন হয়েছে।")
    else:
        await update.effective_message.reply_text("❌ কোনো সংযোগ নেই।")


async def connect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        chat_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    user = update.effective_user
    try:
        m = await context.bot.get_chat_member(chat_id, user.id)
    except Exception:
        return await query.edit_message_text("❌ ওই গ্রুপে বট নেই বা অ্যাক্সেস নেই।")
    if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await query.edit_message_text("❌ আপনি ওই গ্রুপের অ্যাডমিন নন।")
    db.set_connection(user.id, chat_id)
    try:
        title = (await context.bot.get_chat(chat_id)).title or str(chat_id)
    except Exception:
        title = str(chat_id)
    await query.edit_message_text(
        f"🔗 <b>{title}</b> গ্রুপে কানেক্টেড!\n"
        "এখন PM-এ কমান্ড দিলে এই গ্রুপে কাজ করবে।",
        parse_mode=ParseMode.HTML,
    )


async def _admin_groups(context, user_id):
    """Known groups where user_id is admin/owner. Returns [(chat_id, title)]."""
    out = []
    for row in db.list_known_chats():
        try:
            m = await context.bot.get_chat_member(row["chat_id"], user_id)
        except Exception:
            continue
        if m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            out.append((row["chat_id"], row["title"] or str(row["chat_id"])))
    return out


# ------------------------------------------------------------------- router
async def connection_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs before every command handler (group=-1).

    In PM, route the command to the connected group (or auto-connect when the
    user admins exactly one known group), so command handlers transparently
    act on the group. Admin rights are re-verified on every routed command.
    """
    msg = update.effective_message
    if not msg or not msg.text or not msg.text.startswith("/"):
        return
    chat = update.effective_chat
    if not chat or chat.type != "private":
        return
    cmd = msg.text.split()[0].split("@")[0].lower()
    if cmd in _LOCAL_CMDS:
        return
    user = update.effective_user
    target = db.get_connection(user.id)
    auto_note = ""
    if not target:
        # No manual connection — secure auto-connect for the single-group case.
        groups = await _admin_groups(context, user.id)
        if len(groups) == 1:
            target = groups[0][0]
            db.set_connection(user.id, target)
            auto_note = (f"🔗 <b>{groups[0][1]}</b> গ্রুপে স্বয়ংক্রিয়ভাবে "
                         "কানেক্টেড!\n\n")
        elif not groups:
            return await msg.reply_text(
                "❌ কোনো গ্রুপে আপনাকে অ্যাডমিন হিসেবে পাইনি।\n\n"
                "1️⃣ বটকে গ্রুপে অ্যাড করে <b>অ্যাডমিন</b> করুন\n"
                "2️⃣ গ্রুপে গিয়ে <code>/connect</code> লিখুন\n"
                "3️⃣ তারপর এখানে (PM-এ) কমান্ড দিন",
                parse_mode=ParseMode.HTML)
        else:
            return await msg.reply_text(
                "🔗 আপনি একাধিক গ্রুপের অ্যাডমিন — কোন গ্রুপে কাজ করবে বেছে নিন: "
                "/connect",
                parse_mode=ParseMode.HTML)
    try:
        member = await context.bot.get_chat_member(target, user.id)
    except Exception:
        db.del_connection(user.id)
        return await msg.reply_text(
            "❌ গ্রুপের সাথে সংযোগ পাওয়া যাচ্ছে না (বট হয়তো রিমুভ হয়েছে)। "
            "/connect দিয়ে আবার কানেক্ট করুন।"
        )
    if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        db.del_connection(user.id)
        return await msg.reply_text(
            "❌ আপনি আর ওই গ্রুপের অ্যাডমিন নন — সংযোগ বাতিল করা হয়েছে।"
        )
    if auto_note:
        await msg.reply_text(auto_note, parse_mode=ParseMode.HTML)
    try:
        real_chat = await context.bot.get_chat(target)
    except Exception:
        return await msg.reply_text("❌ গ্রুপ খুঁজে পাওয়া যাচ্ছে না।")
    msg.chat = real_chat  # downstream handlers now see the group


def register(app):
    app.add_handler(MessageHandler(filters.ALL, record_chat), group=-2)
    app.add_handler(MessageHandler(filters.COMMAND, connection_router), group=-1)
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("disconnect", disconnect_cmd))
    app.add_handler(CallbackQueryHandler(connect_cb, pattern=r"^connect:"))
