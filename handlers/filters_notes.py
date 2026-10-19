"""Filters + Notes.

Filters: /filter <keyword> <text> | /filters | /stop <kw> | /stopall
Notes:   /save <name> <text> | /get <name> | /#name | /notes | /clear | /clearall
         /privatenotes <on|off>
Supports {first} {last} {username} {chatname} placeholders and
[label](url) inline buttons in the reply text.
"""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from utils import check_admin, extract_buttons, fill_placeholders, is_user_admin, clean_reply


def _send_formatted(message, chat, user, raw_text, count=0):
    text = fill_placeholders(raw_text, user, chat, count)
    clean, markup = extract_buttons(text)
    return message.reply_text(clean, parse_mode=ParseMode.HTML, reply_markup=markup,
                              disable_web_page_preview=True)


# --------------------------------------------------------------- filters
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if len(context.args) < 2:
        return await update.effective_message.reply_text("ব্যবহার: /filter <শব্দ> <উত্তর>")
    keyword = context.args[0]
    reply = " ".join(context.args[1:])
    db.save_filter(update.effective_chat.id, keyword, reply)
    await update.effective_message.reply_text(f"✅ ফিল্টার সেভ: {keyword}")


async def list_filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kws = db.list_filters(update.effective_chat.id)
    if not kws:
        return await update.effective_message.reply_text("কোনো ফিল্টার নেই।")
    await update.effective_message.reply_text("🔎 ফিল্টার:\n• " + "\n• ".join(kws))


async def stop_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /stop <শব্দ>")
    if db.delete_filter(update.effective_chat.id, context.args[0]):
        await update.effective_message.reply_text(f"✅ ফিল্টার মুছেছে: {context.args[0]}")
    else:
        await update.effective_message.reply_text("❌ এমন ফিল্টার নেই।")


async def stopall_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.delete_all_filters(update.effective_chat.id)
    await update.effective_message.reply_text("✅ সব ফিল্টার মুছে ফেলা হয়েছে।")


async def filter_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    text = msg.text.lower()
    # longest keyword first so multi-word filters win
    for kw in sorted(db.list_filters(chat.id), key=len, reverse=True):
        if kw in text:
            reply = db.get_filter(chat.id, kw)
            if reply:
                try:
                    count = await chat.get_member_count()
                except Exception:
                    count = 0
                await _send_formatted(msg, chat, msg.from_user, reply, count)
            break


# ----------------------------------------------------------------- notes
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if len(context.args) < 2:
        return await update.effective_message.reply_text("ব্যবহার: /save <নাম> <টেক্সট>")
    name = context.args[0].lstrip("#").lower()
    reply = " ".join(context.args[1:])
    db.save_note(update.effective_chat.id, name, reply)
    await update.effective_message.reply_text(f"📝 নোট সেভ: #{name}")


async def get_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /get <নাম>")
    name = context.args[0].lstrip("#").lower()
    reply = db.get_note(update.effective_chat.id, name)
    if not reply:
        return await update.effective_message.reply_text("❌ এমন নোট নেই।")
    chat = update.effective_chat
    if db.get_privatenotes(chat.id) and chat.type != "private":
        try:
            await context.bot.send_message(
                update.effective_user.id,
                fill_placeholders(reply, update.effective_user, chat),
                parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            await update.effective_message.reply_text("📩 নোটটি প্রাইভেটে পাঠানো হয়েছে।")
        except Exception:
            await update.effective_message.reply_text("❌ আপনাকে মেসেজ পাঠাতে পারছি না — আগে বটকে /start দিন।")
        return
    try:
        count = await chat.get_member_count()
    except Exception:
        count = 0
    await _send_formatted(update.effective_message, chat, update.effective_user, reply, count)


async def hashtag_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    txt = msg.text.strip()
    if not txt.startswith("#") or " " in txt.split("\n")[0]:
        return
    name = txt[1:].split()[0].lower()
    reply = db.get_note(chat.id, name)
    if reply:
        try:
            count = await chat.get_member_count()
        except Exception:
            count = 0
        await _send_formatted(msg, chat, msg.from_user, reply, count)


async def list_notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = db.list_notes(update.effective_chat.id)
    if not names:
        return await update.effective_message.reply_text("কোনো নোট নেই।")
    await update.effective_message.reply_text("📝 নোট:\n• #" + "\n• #".join(names))


async def clear_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /clear <নাম>")
    if db.delete_note(update.effective_chat.id, context.args[0]):
        await update.effective_message.reply_text(f"✅ নোট মুছেছে: #{context.args[0]}")
    else:
        await update.effective_message.reply_text("❌ এমন নোট নেই।")


async def clearall_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.delete_all_notes(update.effective_chat.id)
    await update.effective_message.reply_text("✅ সব নোট মুছে ফেলা হয়েছে।")


async def privatenotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in ("on", "off"):
        cur = "on" if db.get_privatenotes(chat_id) else "off"
        return await update.effective_message.reply_text(
            f"বর্তমান: {cur}\nব্যবহার: /privatenotes <on|off>")
    db.set_privatenotes(chat_id, context.args[0].lower() == "on")
    await update.effective_message.reply_text(f"✅ Private notes {context.args[0].lower()}।")


def register(app):
    for cmd, fn in [
        ("filter", add_filter), ("filters", list_filter_cmd),
        ("stop", stop_filter), ("stopall", stopall_filters),
        ("save", save_note), ("get", get_note_cmd), ("notes", list_notes_cmd),
        ("clear", clear_note), ("clearall", clearall_notes),
        ("privatenotes", privatenotes),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_watcher), group=4)
    app.add_handler(MessageHandler(filters.Regex(r"^#[^\s]+"), hashtag_watcher), group=5)
