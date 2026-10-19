"""Admin commands: ban/unban/tban/kick/mute/tmute/unmute/promote/demote/
pin/unpin/unpinall/announce/purge/del."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

import database as db
from utils import (
    clean_reply,
    MUTE_PERMISSIONS,
    UNMUTE_PERMISSIONS,
    check_admin,
    command_text,
    extract_buttons,
    get_target_user,
    mention_html,
    parse_time,
    safe_delete,
    user_link,
)


async def _punish_ban(chat, user_id, until=None):
    await chat.ban_member(user_id, until_date=until)


async def _punish_kick(chat, user_id):
    await chat.ban_member(user_id)
    await chat.unban_member(user_id)


async def _punish_mute(chat, user_id, until=None):
    await chat.restrict_member(user_id, MUTE_PERMISSIONS, until_date=until)


PUNISH = {"ban": _punish_ban, "kick": _punish_kick, "mute": _punish_mute}


# ---------------------------------------------------------------- ban / tban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    try:
        await update.effective_chat.ban_member(target)
        await update.effective_message.reply_text(
            f"🔨 {user_link(target)} ব্যান করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ ব্যান করা যায়নি: {e}")


async def tban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if msg.reply_to_message:
        # /tban 5m  (reply)
        if not context.args:
            return await msg.reply_text("ব্যবহার: /tban <সময়: 5m/2h/1d/1w> (রিপ্লাই করে)")
        until = parse_time(context.args[0])
        target = msg.reply_to_message.from_user.id
    else:
        # /tban <ID/@username> 5m
        if len(context.args) < 2:
            return await msg.reply_text("ব্যবহার: /tban <ID/@username> <সময়: 5m/2h/1d/1w>")
        until = parse_time(context.args[1])
        target, terr = await get_target_user(update, context)
        if terr:
            return await msg.reply_text(terr)
    if not until:
        return await msg.reply_text("❌ সময় ভুল! যেমন: 5m, 2h, 1d, 1w")
    try:
        await update.effective_chat.ban_member(target, until_date=until)
        await msg.reply_text(
            f"⏳ {user_link(target)} সাময়িক ব্যান করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.reply_text(f"❌ ব্যান করা যায়নি: {e}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr + "\n💡 ব্যানড ইউজারের ID বা @username দিন।")
    try:
        await update.effective_chat.unban_member(target)
        await update.effective_message.reply_text(
            f"✅ {user_link(target)} আনব্যান করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ আনব্যান করা যায়নি: {e}")


# ------------------------------------------------------------------ kick
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    try:
        await update.effective_chat.ban_member(target)
        await update.effective_chat.unban_member(target)
        await update.effective_message.reply_text(
            f"👢 {user_link(target)} কিক করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ কিক করা যায়নি: {e}")


# ---------------------------------------------------------- mute / tmute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    try:
        await update.effective_chat.restrict_member(target, MUTE_PERMISSIONS)
        await update.effective_message.reply_text(
            f"🔇 {user_link(target)} মিউট করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ মিউট করা যায়নি: {e}")


async def tmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if msg.reply_to_message:
        if not context.args:
            return await msg.reply_text("ব্যবহার: /tmute <সময়: 5m/2h/1d/1w> (রিপ্লাই করে)")
        until = parse_time(context.args[0])
        target = msg.reply_to_message.from_user.id
    else:
        if len(context.args) < 2:
            return await msg.reply_text("ব্যবহার: /tmute <ID/@username> <সময়>")
        until = parse_time(context.args[1])
        target, terr = await get_target_user(update, context)
        if terr:
            return await msg.reply_text(terr)
    if not until:
        return await msg.reply_text("❌ সময় ভুল! যেমন: 5m, 2h, 1d, 1w")
    try:
        await update.effective_chat.restrict_member(target, MUTE_PERMISSIONS, until_date=until)
        await msg.reply_text(f"⏳ {user_link(target)} সাময়িক মিউট করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.reply_text(f"❌ মিউট করা যায়নি: {e}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    try:
        await update.effective_chat.restrict_member(target, UNMUTE_PERMISSIONS)
        await update.effective_message.reply_text(
            f"🔊 {user_link(target)} আনমিউট করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ আনমিউট করা যায়নি: {e}")


# ------------------------------------------------------- promote / demote
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_promote=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    title = " ".join(context.args[1:]) if len(context.args) > 1 else None
    try:
        await update.effective_chat.promote_member(
            target,
            can_change_info=True, can_delete_messages=True, can_invite_users=True,
            can_restrict_members=True, can_pin_messages=True, can_promote_members=False,
            can_manage_video_chats=True,
        )
        if title:
            try:
                await context.bot.set_chat_administrator_custom_title(update.effective_chat.id, target, title[:16])
            except Exception:
                pass
        await update.effective_message.reply_text(f"⬆️ {user_link(target)} প্রমোট করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ প্রমোট করা যায়নি: {e}")


async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_promote=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    try:
        await update.effective_chat.promote_member(
            target,
            can_change_info=False, can_delete_messages=False, can_invite_users=False,
            can_restrict_members=False, can_pin_messages=False, can_promote_members=False,
            can_manage_video_chats=False,
        )
        await update.effective_message.reply_text(f"⬇️ {user_link(target)} ডিমোট করা হয়েছে।", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ ডিমোট করা যায়নি: {e}")


# ------------------------------------------------------------ pin / unpin
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_pin=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("📌 কোন মেসেজে রিপ্লাই করে /pin দিন।")
    try:
        await update.effective_chat.pin_message(msg.reply_to_message.message_id, disable_notification=True)
        await msg.reply_text("📌 পিন করা হয়েছে।")
    except Exception as e:
        await msg.reply_text(f"❌ পিন করা যায়নি: {e}")


async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_pin=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    try:
        if msg.reply_to_message:
            await update.effective_chat.unpin_message(msg.reply_to_message.message_id)
        else:
            await update.effective_chat.unpin_message()
        await msg.reply_text("📌 আনপিন করা হয়েছে।")
    except Exception as e:
        await msg.reply_text(f"❌ আনপিন করা যায়নি: {e}")


async def unpinall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_pin=True)
    if not ok:
        return await clean_reply(update, context, err)
    try:
        await update.effective_chat.unpin_all_messages()
        await update.effective_message.reply_text("📌 সব পিন মুছে ফেলা হয়েছে।")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ করা যায়নি: {e}")


# ---------------------------------------------------------- announce
async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = command_text(update)
    do_pin = False
    if text[:4].lower() == "pin ":
        do_pin = True
        text = text[4:].strip()
    ok, err = await check_admin(update, context, need_pin=do_pin)
    if not ok:
        return await clean_reply(update, context, err)
    if not text:
        return await update.effective_message.reply_text(
            "ব্যবহার: /announce <মেসেজ>\nপিনসহ: /announce pin <মেসেজ>\n"
            "বাটন: [লেখা](https://লিংক) — রঙিন: [লেখা](https://লিংক|red)")
    clean, markup = extract_buttons(text)
    body = f"📢 <b>ঘোষণা</b>\n\n{clean}"
    try:
        sent = await context.bot.send_message(
            update.effective_chat.id, body, parse_mode=ParseMode.HTML,
            reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        return await update.effective_message.reply_text(f"❌ পাঠানো যায়নি: {e}")
    if do_pin:
        try:
            await update.effective_chat.pin_message(sent.message_id, disable_notification=True)
        except Exception as e:
            return await update.effective_message.reply_text(
                f"📢 পাঠানো হয়েছে, কিন্তু পিন করা যায়নি: {e}")
    await update.effective_message.reply_text("📢 ঘোষণা পাঠানো হয়েছে।")


# ---------------------------------------------------------- purge / del
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("🧹 কোন মেসেজে রিপ্লাই করে /purge দিন — ওই মেসেজ থেকে এ পর্যন্ত সব ডিলিট হবে।")
    start = msg.reply_to_message.message_id
    end = msg.message_id
    if end - start > 100:
        start = end - 100  # Telegram bulk-delete-ish safety cap
    deleted = 0
    for mid in range(start, end + 1):
        try:
            await context.bot.delete_message(msg.chat_id, mid)
            deleted += 1
        except Exception:
            pass
    note = await msg.reply_text(f"🧹 {deleted}টি মেসেজ ডিলিট করা হয়েছে।")
    # remove the confirmation after a few seconds is optional; keep it


async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("🗑️ কোন মেসেজে রিপ্লাই করে /del দিন।")
    await safe_delete(msg.reply_to_message)
    await safe_delete(msg)


def register(app):
    for cmd, fn in [
        ("ban", ban), ("tban", tban), ("unban", unban), ("kick", kick),
        ("mute", mute), ("tmute", tmute), ("unmute", unmute),
        ("promote", promote), ("demote", demote),
        ("pin", pin), ("unpin", unpin), ("unpinall", unpinall),
        ("purge", purge), ("del", delete_msg), ("announce", announce),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
