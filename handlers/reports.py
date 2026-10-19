"""Reports: /report (reply) -> notifies admins with action buttons.
/reports <on|off> toggles the feature."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
from handlers.admin import PUNISH
from utils import check_admin, user_link, clean_reply


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if chat.type == "private":
        return await msg.reply_text("❌ /report শুধু গ্রুপে কাজ করে।")
    if not db.get_reports(chat.id):
        return await msg.reply_text("❌ এই গ্রুপে reports বন্ধ আছে।")
    if not msg.reply_to_message:
        return await msg.reply_text("ব্যবহার: অপরাধমূলক মেসেজে রিপ্লাই করে /report দিন।")
    target = msg.reply_to_message.from_user
    reporter = msg.from_user
    if target.id == reporter.id:
        return await msg.reply_text("❌ নিজেকে রিপোর্ট করা যায় না।")

    text = (f"🚨 <b>রিপোর্ট</b>\n"
            f"গ্রুপ: {chat.title}\n"
            f"রিপোর্টার: {user_link(reporter.id, reporter.first_name)}\n"
            f"অভিযুক্ত: {user_link(target.id, target.first_name)}\n"
            f"মেসেজ: {msg.reply_to_message.message_id}")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔨 Ban", callback_data=f"rep:ban:{chat.id}:{target.id}:{msg.reply_to_message.message_id}"),
        InlineKeyboardButton("👢 Kick", callback_data=f"rep:kick:{chat.id}:{target.id}:{msg.reply_to_message.message_id}"),
        InlineKeyboardButton("🔇 Mute", callback_data=f"rep:mute:{chat.id}:{target.id}:{msg.reply_to_message.message_id}"),
        InlineKeyboardButton("🗑️ Del", callback_data=f"rep:del:{chat.id}:{target.id}:{msg.reply_to_message.message_id}"),
    ]])
    sent = 0
    try:
        admins = await chat.get_administrators()
    except Exception:
        return await msg.reply_text("❌ অ্যাডমিন তালিকা পাওয়া যায়নি।")
    for admin in admins:
        if admin.user.is_bot:
            continue
        try:
            await context.bot.send_message(admin.user.id, text, parse_mode=ParseMode.HTML, reply_markup=kb)
            sent += 1
        except Exception:
            pass  # admin hasn't started the bot in PM
    await msg.reply_text(f"✅ রিপোর্ট {sent} জন অ্যাডমিনের কাছে পাঠানো হয়েছে।")


async def reports_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in ("on", "off"):
        cur = db.get_reports(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'on' if cur else 'off'}\nব্যবহার: /reports <on|off>")
    db.set_reports(chat_id, context.args[0].lower() == "on")
    await update.effective_message.reply_text(f"✅ Reports {context.args[0].lower()}।")


async def report_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    action, chat_id, target_id, msg_id = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
    # only admins of that chat may act
    try:
        member = await context.bot.get_chat_member(chat_id, query.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await query.answer("শুধু অ্যাডমিনরা পারবেন!", show_alert=True)
    except Exception:
        return await query.answer("যাচাই করা যায়নি।", show_alert=True)
    try:
        if action == "del":
            await context.bot.delete_message(chat_id, msg_id)
        else:
            chat = await context.bot.get_chat(chat_id)
            await PUNISH[action](chat, target_id)
        await query.answer(f"✅ {action} সম্পন্ন!")
        await query.edit_message_text(f"✅ অ্যাকশন নেওয়া হয়েছে: {action} (by {query.from_user.first_name})")
    except Exception as e:
        await query.answer(f"❌ ব্যর্থ: {e}", show_alert=True)


def register(app):
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("reports", reports_toggle))
    app.add_handler(CallbackQueryHandler(report_action, pattern=r"^rep:"))
