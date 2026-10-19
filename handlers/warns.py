"""Warn system: /warn /unwarn /warns /resetwarns /warnlimit /warnmode
/addwarn /nowarn /warnfilters (+ auto-warn on keyword filters)."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from handlers.admin import PUNISH
from utils import (
    clean_reply,
    check_admin,
    get_target_user,
    is_user_admin,
    user_link,
)

VALID_MODES = ("ban", "mute", "kick")


async def _apply_limit_action(chat, user_id, mode):
    fn = PUNISH.get(mode, PUNISH["ban"])
    await fn(chat, user_id)


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await clean_reply(update, context, terr)
    if await is_user_admin(update.effective_chat, target):
        return await clean_reply(update, context, "❌ অ্যাডমিনকে warn করা যায় না।")
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "কোনো কারণ দেওয়া হয়নি"
    chat_id = update.effective_chat.id
    count = db.add_warn(chat_id, target)
    limit = db.get_warn_limit(chat_id)
    msg = (f"⚠️ {user_link(target)} কে warn দেওয়া হয়েছে ({count}/{limit}).\n"
           f"কারণ: {reason}")
    if count >= limit:
        mode = db.get_warn_mode(chat_id)
        try:
            await _apply_limit_action(update.effective_chat, target, mode)
            msg += f"\n🚫 লিমিট পার হওয়ায় {mode} করা হয়েছে।"
        except Exception as e:
            msg += f"\n❌ অ্যাকশন নেওয়া যায়নি: {e}"
        db.reset_warns(chat_id, target)
    await clean_reply(update, context, msg, parse_mode=ParseMode.HTML)


async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await clean_reply(update, context, terr)
    count = db.remove_warn(update.effective_chat.id, target)
    await clean_reply(update, context, 
        f"✅ {user_link(target)} এর একটি warn কমানো হয়েছে। বর্তমান: {count}", parse_mode=ParseMode.HTML)


async def warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, terr = await get_target_user(update, context)
    if terr:
        return await clean_reply(update, context, terr)
    chat_id = update.effective_chat.id
    count = db.get_warns(chat_id, target)
    limit = db.get_warn_limit(chat_id)
    await clean_reply(update, context, 
        f"⚠️ {user_link(target)} এর warn: {count}/{limit}", parse_mode=ParseMode.HTML)


async def resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    target, terr = await get_target_user(update, context)
    if terr:
        return await clean_reply(update, context, terr)
    db.reset_warns(update.effective_chat.id, target)
    await clean_reply(update, context, 
        f"✅ {user_link(target)} এর সব warn রিসেট করা হয়েছে।", parse_mode=ParseMode.HTML)


async def warnlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        return await clean_reply(update, context, 
            f"বর্তমান warn লিমিট: {db.get_warn_limit(chat_id)}\nব্যবহার: /warnlimit <সংখ্যা>")
    db.set_warn_limit(chat_id, int(context.args[0]))
    await clean_reply(update, context, f"✅ Warn লিমিট {context.args[0]} করা হয়েছে।")


async def warnmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in VALID_MODES:
        return await clean_reply(update, context, 
            f"বর্তমান warn মোড: {db.get_warn_mode(chat_id)}\nব্যবহার: /warnmode <ban|mute|kick>")
    db.set_warn_mode(chat_id, context.args[0].lower())
    await clean_reply(update, context, f"✅ Warn মোড {context.args[0].lower()} করা হয়েছে।")


async def addwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await clean_reply(update, context, "ব্যবহার: /addwarn <শব্দ> — ওই শব্দ লিখলেই অটো warn হবে।")
    keyword = " ".join(context.args)
    db.add_warn_filter(update.effective_chat.id, keyword)
    await clean_reply(update, context, f"✅ Warn ফিল্টার যোগ: {keyword}")


async def nowarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await clean_reply(update, context, "ব্যবহার: /nowarn <শব্দ>")
    keyword = " ".join(context.args)
    if db.remove_warn_filter(update.effective_chat.id, keyword):
        await clean_reply(update, context, f"✅ Warn ফিল্টার মুছেছে: {keyword}")
    else:
        await clean_reply(update, context, "❌ এমন warn ফিল্টার নেই।")


async def warnfilters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = db.list_warn_filters(update.effective_chat.id)
    if not words:
        return await clean_reply(update, context, "কোনো warn ফিল্টার নেই।")
    await clean_reply(update, context, "⚠️ Warn ফিল্টার:\n• " + "\n• ".join(words))


async def auto_warn_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-warn users whose message matches a warn-filter keyword."""
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    if await is_user_admin(chat, msg.from_user.id):
        return
    text = msg.text.lower()
    chat_id = chat.id
    for keyword in db.list_warn_filters(chat_id):
        if keyword in text:
            count = db.add_warn(chat_id, msg.from_user.id)
            limit = db.get_warn_limit(chat_id)
            reply = (f"⚠️ {user_link(msg.from_user.id, msg.from_user.first_name)} "
                     f"নিষিদ্ধ শব্দ ব্যবহার করায় warn ({count}/{limit}).")
            if count >= limit:
                mode = db.get_warn_mode(chat_id)
                try:
                    await _apply_limit_action(chat, msg.from_user.id, mode)
                    reply += f" লিমিট পার হওয়ায় {mode} করা হয়েছে।"
                except Exception:
                    pass
                db.reset_warns(chat_id, msg.from_user.id)
            await clean_reply(update, context, reply, parse_mode=ParseMode.HTML)
            break


def register(app):
    for cmd, fn in [
        ("warn", warn), ("unwarn", unwarn), ("warns", warns),
        ("resetwarns", resetwarns), ("warnlimit", warnlimit), ("warnmode", warnmode),
        ("addwarn", addwarn), ("nowarn", nowarn), ("warnfilters", warnfilters),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_warn_watcher), group=3)
