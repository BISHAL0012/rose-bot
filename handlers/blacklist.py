"""Blacklist: /addblacklist | /unblacklist | /blacklist | /blacklistmode
/blsticker | /unblsticker | /blstickers.

Trigger words are deleted and the configured mode is applied.
Blacklisted stickers are deleted on send.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from handlers.admin import PUNISH
from utils import check_admin, is_user_admin, safe_delete, user_link, clean_reply

VALID_MODES = ("off", "del", "warn", "mute", "kick", "ban")


async def addblacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /addblacklist <শব্দ>")
    word = " ".join(context.args)
    db.add_blacklist(update.effective_chat.id, word)
    await update.effective_message.reply_text(f"✅ ব্ল্যাকলিস্টে যোগ: {word}")


async def unblacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /unblacklist <শব্দ>")
    word = " ".join(context.args)
    if db.remove_blacklist(update.effective_chat.id, word):
        await update.effective_message.reply_text(f"✅ ব্ল্যাকলিস্ট থেকে মুছেছে: {word}")
    else:
        await update.effective_message.reply_text("❌ ব্ল্যাকলিস্টে এমন শব্দ নেই।")


async def blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = db.list_blacklist(update.effective_chat.id)
    if not words:
        return await update.effective_message.reply_text("ব্ল্যাকলিস্ট খালি।")
    await update.effective_message.reply_text("🚫 ব্ল্যাকলিস্ট:\n• " + "\n• ".join(words))


async def blacklistmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in VALID_MODES:
        return await update.effective_message.reply_text(
            f"বর্তমান: {db.get_blacklist_mode(chat_id)}\n"
            "ব্যবহার: /blacklistmode <off|del|warn|ban|mute|kick>")
    db.set_blacklist_mode(chat_id, context.args[0].lower())
    await update.effective_message.reply_text(f"✅ Blacklist মোড: {context.args[0].lower()}")


async def blsticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.sticker:
        return await msg.reply_text("ব্যবহার: কোনো স্টিকারে রিপ্লাই করে /blsticker দিন।")
    db.add_blsticker(update.effective_chat.id, msg.reply_to_message.sticker.file_id)
    await msg.reply_text("✅ স্টিকার ব্ল্যাকলিস্টে যোগ হয়েছে।")


async def unblsticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.sticker:
        return await msg.reply_text("ব্যবহার: ওই স্টিকারে রিপ্লাই করে /unblsticker দিন।")
    if db.remove_blsticker(update.effective_chat.id, msg.reply_to_message.sticker.file_id):
        await msg.reply_text("✅ স্টিকার ব্ল্যাকলিস্ট থেকে মুছেছে।")
    else:
        await msg.reply_text("❌ এই স্টিকার ব্ল্যাকলিস্টে নেই।")


async def blstickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stickers = db.list_blstickers(update.effective_chat.id)
    await update.effective_message.reply_text(
        f"🚫 ব্ল্যাকলিস্টেড স্টিকার: {len(stickers)}টি")


async def blacklist_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    if await is_user_admin(chat, msg.from_user.id):
        return
    chat_id = chat.id

    # blacklisted stickers
    if msg.sticker and db.is_blsticker(chat_id, msg.sticker.file_id):
        await safe_delete(msg)
        return

    text = (msg.text or "") + " " + (msg.caption or "")
    if not text.strip() or text.startswith("/"):
        return
    mode = db.get_blacklist_mode(chat_id)
    if mode == "off":
        return
    lowered = text.lower()
    for word in db.list_blacklist(chat_id):
        if word in lowered:
            await safe_delete(msg)
            uid = msg.from_user.id
            if mode == "warn":
                count = db.add_warn(chat_id, uid)
                limit = db.get_warn_limit(chat_id)
                await context.bot.send_message(
                    chat_id,
                    f"⚠️ {user_link(uid, msg.from_user.first_name)} ব্ল্যাকলিস্ট শব্দ ব্যবহার করায় warn ({count}/{limit}).",
                    parse_mode="HTML")
                if count >= limit:
                    wmode = db.get_warn_mode(chat_id)
                    try:
                        await PUNISH[wmode](chat, uid)
                    except Exception:
                        pass
                    db.reset_warns(chat_id, uid)
            elif mode in ("ban", "kick", "mute"):
                try:
                    await PUNISH[mode](chat, uid)
                    await context.bot.send_message(
                        chat_id,
                        f"🚫 {user_link(uid, msg.from_user.first_name)} ব্ল্যাকলিস্ট শব্দ ব্যবহার করায় {mode}।",
                        parse_mode="HTML")
                except Exception:
                    pass
            break


def register(app):
    for cmd, fn in [
        ("addblacklist", addblacklist), ("unblacklist", unblacklist),
        ("blacklist", blacklist), ("blacklistmode", blacklistmode),
        ("blsticker", blsticker), ("unblsticker", unblsticker),
        ("blstickers", blstickers),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, blacklist_watcher), group=6)
