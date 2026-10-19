"""Welcome/Goodbye + button captcha (welcomemute) + rules."""

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)

import database as db
from utils import (
    clean_reply,
    MUTE_PERMISSIONS,
    UNMUTE_PERMISSIONS,
    check_admin,
    command_text,
    extract_buttons,
    fill_placeholders,
    is_user_admin,
    safe_delete,
)

CAPTCHA_TTL = 300  # 5 minutes


def _on_off(val: str):
    v = val.lower()
    if v in ("on", "yes", "y"):
        return True
    if v in ("off", "no", "n"):
        return False
    return None


# ------------------------------------------------------------- welcome cmds
async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    text = command_text(update)
    if not text:
        return await update.effective_message.reply_text(
            "ব্যবহার: /setwelcome <মেসেজ>\nপ্লেসহোল্ডার: {first} {last} {fullname} {username} {id} {chatname} {count}")
    db.set_welcome(update.effective_chat.id, text)
    await update.effective_message.reply_text("✅ Welcome মেসেজ সেট হয়েছে।")


async def setwelcomemedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    reply = msg.reply_to_message
    photo = None
    if reply and reply.photo:
        photo = reply.photo[-1]
    elif msg.photo:
        photo = msg.photo[-1]
    if not photo:
        return await msg.reply_text(
            "❌ একটি ছবিতে রিপ্লাই করে /setwelcomemedia দিন।")
    db.set_welcome_media(update.effective_chat.id, photo.file_id)
    await msg.reply_text("✅ Welcome photo সেট হয়েছে! এখন welcome মেসেজ ছবিসহ আসবে।")


async def clearwelcomemedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.clear_welcome_media(update.effective_chat.id)
    await update.effective_message.reply_text("✅ Welcome photo মুছে ফেলা হয়েছে।")


async def resetwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.reset_welcome(update.effective_chat.id)
    await update.effective_message.reply_text("✅ Welcome মেসেজ রিসেট হয়েছে।")


async def welcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or _on_off(context.args[0]) is None:
        _, on = db.get_welcome(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'on' if on else 'off'}\nব্যবহার: /welcome <on|off>")
    db.set_welcome_on(chat_id, _on_off(context.args[0]))
    await update.effective_message.reply_text(f"✅ Welcome {_on_off(context.args[0]) and 'on' or 'off'}।")


async def setgoodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    text = command_text(update)
    if not text:
        return await update.effective_message.reply_text("ব্যবহার: /setgoodbye <মেসেজ>")
    db.set_goodbye(update.effective_chat.id, text)
    await update.effective_message.reply_text("✅ Goodbye মেসেজ সেট হয়েছে।")


async def resetgoodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.reset_goodbye(update.effective_chat.id)
    await update.effective_message.reply_text("✅ Goodbye মেসেজ রিসেট হয়েছে।")


async def goodbye_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or _on_off(context.args[0]) is None:
        _, on = db.get_goodbye(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'on' if on else 'off'}\nব্যবহার: /goodbye <on|off>")
    db.set_goodbye_on(chat_id, _on_off(context.args[0]))
    await update.effective_message.reply_text(f"✅ Goodbye {_on_off(context.args[0]) and 'on' or 'off'}।")


async def welcomemute_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or _on_off(context.args[0]) is None:
        cur = db.get_welcomemute(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'on' if cur else 'off'}\nব্যবহার: /welcomemute <on|off>\n"
            "on থাকলে নতুন মেম্বারকে বাটনে ট্যাপ করে মানুষ প্রমাণ করতে হবে।")
    db.set_welcomemute(chat_id, _on_off(context.args[0]))
    await update.effective_message.reply_text(f"✅ Welcomemute {_on_off(context.args[0]) and 'on' or 'off'}।")


async def cleanwelcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or _on_off(context.args[0]) is None:
        cur = db.get_cleanwelcome(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'on' if cur else 'off'}\nব্যবহার: /cleanwelcome <on|off>")
    db.set_cleanwelcome(chat_id, _on_off(context.args[0]))
    await update.effective_message.reply_text(f"✅ Cleanwelcome {_on_off(context.args[0]) and 'on' or 'off'}।")


# ------------------------------------------------------- join/leave handler
async def _autodelete_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id, msg_id, user_id = context.job.data
    # captcha বাকি থাকলে মেসেজ ডিলিট কোরো না (বাটন দরকার)
    if user_id and db.has_pending_captcha(chat_id, user_id):
        return
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


async def _async_delayed_delete(bot, chat_id: int, msg_id: int, delay: int, user_id=None):
    """Fallback when job_queue (APScheduler) is not installed."""
    await asyncio.sleep(delay)
    if user_id and db.has_pending_captcha(chat_id, user_id):
        return
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def _schedule_autodelete(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                         msg_id: int, delay: int, user_id=None, prefix="d"):
    if context.job_queue:
        context.job_queue.run_once(
            _autodelete_job, delay,
            data=(chat_id, msg_id, user_id),
            name=f"{prefix}_{chat_id}_{msg_id}")
    else:
        asyncio.create_task(
            _async_delayed_delete(context.bot, chat_id, msg_id, delay, user_id))


async def welcometimer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args:
        cur = db.get_welcome_timer(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'off' if cur <= 0 else f'{cur} সেকেন্ড'}\n"
            "ব্যবহার: /welcometimer <সেকেন্ড|off>\nউদাহরণ: /welcometimer 30")
    arg = context.args[0].lower()
    if arg in ("off", "no", "0"):
        db.set_welcome_timer(chat_id, 0)
        return await update.effective_message.reply_text("✅ Welcome টাইমার বন্ধ।")
    try:
        secs = int(arg)
    except ValueError:
        return await update.effective_message.reply_text(
            "ব্যবহার: /welcometimer <সেকেন্ড|off>\nউদাহরণ: /welcometimer 30")
    if secs < 5 or secs > 86400:
        return await update.effective_message.reply_text("⏱️ ৫ সেকেন্ড থেকে ২৪ ঘণ্টার মধ্যে দিন।")
    db.set_welcome_timer(chat_id, secs)
    await update.effective_message.reply_text(f"✅ Welcome মেসেজ {secs} সেকেন্ড পর অটো ডিলিট হবে।")


async def goodbyetimer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args:
        cur = db.get_goodbye_timer(chat_id)
        return await update.effective_message.reply_text(
            f"বর্তমান: {'off' if cur <= 0 else f'{cur} সেকেন্ড'}\n"
            "ব্যবহার: /goodbyetimer <সেকেন্ড|off>\nউদাহরণ: /goodbyetimer 30")
    arg = context.args[0].lower()
    if arg in ("off", "no", "0"):
        db.set_goodbye_timer(chat_id, 0)
        return await update.effective_message.reply_text("✅ Goodbye টাইমার বন্ধ।")
    try:
        secs = int(arg)
    except ValueError:
        return await update.effective_message.reply_text(
            "ব্যবহার: /goodbyetimer <সেকেন্ড|off>\nউদাহরণ: /goodbyetimer 30")
    if secs < 5 or secs > 86400:
        return await update.effective_message.reply_text("⏱️ ৫ সেকেন্ড থেকে ২৪ ঘণ্টার মধ্যে দিন।")
    db.set_goodbye_timer(chat_id, secs)
    await update.effective_message.reply_text(f"✅ Goodbye মেসেজ {secs} সেকেন্ড পর অটো ডিলিট হবে।")


async def _kick_if_unverified(context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id = context.job.data
    if db.has_pending_captcha(chat_id, user_id):
        db.remove_pending_captcha(chat_id, user_id)
        try:
            await context.bot.ban_member(chat_id, user_id)
            await context.bot.unban_member(chat_id, user_id)
            await context.bot.send_message(
                chat_id, f"⏰ <a href='tg://user?id={user_id}'>user</a> যাচাই না করায় কিক করা হয়েছে।",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle joins and leaves."""
    result = update.chat_member
    if not result:
        return
    chat = result.chat
    user = result.new_chat_member.user
    old = result.old_chat_member.status
    new = result.new_chat_member.status
    chat_id = chat.id

    joined = old in ("left", "kicked", "banned") and new == "member"
    left = new in ("left", "kicked", "banned") and old == "member"
    if user.is_bot:
        return

    if joined:
        text, on = db.get_welcome(chat_id)
        if on:
            try:
                count = await chat.get_member_count()
            except Exception:
                count = 0
            filled = fill_placeholders(text, user, chat, count)
            clean, markup = extract_buttons(filled)
            buttons = list(markup.inline_keyboard) if markup else []
            captcha_on = db.get_welcomemute(chat_id) and not await is_user_admin(chat, user.id)
            if captcha_on:
                try:
                    await chat.restrict_member(user.id, MUTE_PERMISSIONS)
                except Exception:
                    captcha_on = False
            if captcha_on:
                buttons.append([InlineKeyboardButton(
                    "✅ আমি মানুষ (I'm human)",
                    callback_data=f"captcha:{chat_id}:{user.id}")])
                db.add_pending_captcha(chat_id, user.id, CAPTCHA_TTL)
                if context.job_queue:
                    context.job_queue.run_once(_kick_if_unverified, CAPTCHA_TTL,
                                               data=(chat_id, user.id),
                                               name=f"captcha_{chat_id}_{user.id}")
            try:
                media = db.get_welcome_media(chat_id)
                markup = InlineKeyboardMarkup(buttons) if buttons else None
                if media:
                    sent = await context.bot.send_photo(
                        chat_id, photo=media, caption=clean, parse_mode=ParseMode.HTML,
                        reply_markup=markup)
                else:
                    sent = await context.bot.send_message(
                        chat_id, clean, parse_mode=ParseMode.HTML,
                        reply_markup=markup,
                        disable_web_page_preview=True)
                if db.get_cleanwelcome(chat_id):
                    old_id = db.get_last_welcome_msg(chat_id)
                    if old_id:
                        try:
                            await context.bot.delete_message(chat_id, old_id)
                        except Exception:
                            pass
                    db.set_last_welcome_msg(chat_id, sent.message_id)
                timer = db.get_welcome_timer(chat_id)
                if timer > 0:
                    _schedule_autodelete(context, chat_id, sent.message_id,
                                         timer, user.id, "wdel")
            except Exception:
                pass
    elif left:
        text, on = db.get_goodbye(chat_id)
        if on:
            try:
                count = await chat.get_member_count()
            except Exception:
                count = 0
            filled = fill_placeholders(text, user, chat, count)
            clean, markup = extract_buttons(filled)
            try:
                sent = await context.bot.send_message(chat_id, clean, parse_mode=ParseMode.HTML,
                                                      reply_markup=markup,
                                                      disable_web_page_preview=True)
                timer = db.get_goodbye_timer(chat_id)
                if timer > 0:
                    _schedule_autodelete(context, chat_id, sent.message_id,
                                         timer, None, "gdel")
            except Exception:
                pass


async def captcha_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_s, user_id_s = query.data.split(":")
    chat_id, user_id = int(chat_id_s), int(user_id_s)
    if query.from_user.id != user_id:
        return await query.answer("এই বাটন আপনার জন্য নয়!", show_alert=True)
    db.remove_pending_captcha(chat_id, user_id)
    try:
        await context.bot.restrict_member(chat_id, user_id, UNMUTE_PERMISSIONS)
    except Exception:
        pass
    # cancel pending kick job
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"captcha_{chat_id}_{user_id}"):
            job.schedule_removal()
    await query.answer("✅ যাচাই সম্পন্ন!")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# ------------------------------------------------------------------ rules
async def setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    text = command_text(update)
    if not text:
        return await update.effective_message.reply_text("ব্যবহার: /setrules <নিয়মাবলী>")
    db.set_rules(update.effective_chat.id, text)
    await update.effective_message.reply_text("✅ Rules সেট হয়েছে।")


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = db.get_rules(update.effective_chat.id)
    if not text:
        return await update.effective_message.reply_text("এই গ্রুপে কোনো rules সেট করা নেই।")
    chat = update.effective_chat
    if chat.type != "private":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            "📜 Rules (PM-এ দেখুন)", url=f"https://t.me/{context.bot.username}?start=rules_{chat.id}")]])
        await update.effective_message.reply_text(
            "📜 গ্রুপের rules দেখতে নিচের বাটনে ট্যাপ করুন।", reply_markup=kb)
    else:
        await update.effective_message.reply_text(f"📜 Rules:\n\n{text}")


async def clearrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    db.clear_rules(update.effective_chat.id)
    await update.effective_message.reply_text("✅ Rules মুছে ফেলা হয়েছে।")


def register(app):
    for cmd, fn in [
        ("setwelcome", setwelcome), ("resetwelcome", resetwelcome), ("welcome", welcome_toggle),
        ("setwelcomemedia", setwelcomemedia), ("clearwelcomemedia", clearwelcomemedia),
        ("setgoodbye", setgoodbye), ("resetgoodbye", resetgoodbye), ("goodbye", goodbye_toggle),
        ("welcomemute", welcomemute_toggle), ("cleanwelcome", cleanwelcome_toggle),
        ("welcometimer", welcometimer_cmd), ("goodbyetimer", goodbyetimer_cmd),
        ("setrules", setrules), ("rules", rules), ("clearrules", clearrules),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(captcha_button, pattern=r"^captcha:"))
