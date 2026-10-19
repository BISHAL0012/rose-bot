"""Federations: manage several groups together with shared bans.

/newfed <name>       - create a federation (PM or group)
/delfed              - delete your federation (fed owner)
/fedinfo             - show federation details
/joinfed <fed_id>    - link this group to a fed (group admin)
/leavefed            - unlink this group (group admin)
/fban <user> [reason]- ban across ALL fed chats (fed admin)
/unfban <user>       - unban across ALL fed chats (fed admin)
/fedbanlist          - list fed bans
/fedpromote <user>   - add fed admin (fed owner)
/feddemote <user>    - remove fed admin (fed owner)

New members who are fed-banned are banned automatically on join.
"""

import secrets

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ChatMemberHandler, CommandHandler, ContextTypes

import database as db
from utils import check_admin, get_target_user, html_escape, clean_reply


def _new_fed_id() -> str:
    fed_id = secrets.token_hex(4)
    while db.get_fed(fed_id):
        fed_id = secrets.token_hex(4)
    return fed_id


def _resolve_fed(update: Update, user_id: int):
    """Return (fed_id|None, error|None) for fed-admin commands.

    In a group: the chat's linked fed. In PM: the single fed where the
    user is a fed admin.
    """
    chat = update.effective_chat
    if chat.type != "private":
        fed_id = db.get_chat_fed(chat.id)
        if not fed_id:
            return None, "❌ এই গ্রুপ কোনো federation-এ যুক্ত না। /joinfed দিয়ে যুক্ত করুন।"
        return fed_id, None
    mine = [f["fed_id"] for f in db.my_feds(user_id)]
    if len(mine) == 1:
        return mine[0], None
    # also check feds where user is admin but not owner
    return None, ("❌ PM থেকে fed কমান্ড চালাতে একটি fed-linked গ্রুপে গিয়ে চালান, "
                  "অথবা আপনার fed-এর গ্রুপে /fban দিন।")


async def _require_fed_admin(update, user_id: int):
    fed_id, err = _resolve_fed(update, user_id)
    if err:
        return None, err
    if not db.is_fed_admin(fed_id, user_id):
        return None, "❌ আপনি এই federation-এর অ্যাডমিন নন।"
    return fed_id, None


async def fanout_ban(bot, fed_id: str, user_id: int, ban: bool = True):
    """Ban/unban a user in every linked chat. Returns (ok, failed).

    `bot` only needs ban_chat_member/unban_chat_member — mock-friendly.
    """
    ok = failed = 0
    for cid in db.fed_chats(fed_id):
        try:
            if ban:
                await bot.ban_chat_member(cid, user_id)
            else:
                await bot.unban_chat_member(cid, user_id)
            ok += 1
        except Exception:
            failed += 1
    return ok, failed


# ------------------------------------------------------------------ commands
async def newfed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /newfed <নাম>")
    name = " ".join(context.args)[:64]
    fed_id = _new_fed_id()
    db.create_fed(fed_id, name, user.id)
    await update.effective_message.reply_text(
        f"✅ Federation তৈরি!\n\n"
        f"📛 নাম: {html_escape(name)}\n"
        f"🆔 Fed ID: <code>{fed_id}</code>\n\n"
        f"গ্রুপে গিয়ে <code>/joinfed {fed_id}</code> দিয়ে যুক্ত করুন।",
        parse_mode=ParseMode.HTML)


async def delfed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = _resolve_fed(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    fed = db.get_fed(fed_id)
    if not fed or fed["owner_id"] != user.id:
        return await update.effective_message.reply_text("❌ শুধু fed owner ডিলিট করতে পারেন।")
    db.delete_fed(fed_id)
    await update.effective_message.reply_text("✅ Federation ডিলিট হয়েছে।")


async def fedinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        feds = db.my_feds(user.id)
        if not feds:
            return await update.effective_message.reply_text("❌ আপনার কোনো federation নেই। /newfed দিয়ে বানান।")
        lines = ["🌐 <b>আপনার Federations:</b>"]
        for f in feds:
            fed = db.get_fed(f["fed_id"])
            lines.append(
                f"• {html_escape(fed['name'])} — <code>{fed['fed_id']}</code> | "
                f"{len(db.fed_chats(fed['fed_id']))} গ্রুপ | {len(db.fed_banlist(fed['fed_id']))} ব্যান")
        return await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    fed_id = db.get_chat_fed(chat.id)
    if not fed_id:
        return await update.effective_message.reply_text("❌ এই গ্রুপ কোনো federation-এ যুক্ত না।")
    fed = db.get_fed(fed_id)
    await update.effective_message.reply_text(
        f"🌐 <b>Federation info</b>\n\n"
        f"📛 নাম: {html_escape(fed['name'])}\n"
        f"🆔 ID: <code>{fed['fed_id']}</code>\n"
        f"👑 Owner: <code>{fed['owner_id']}</code>\n"
        f"👥 Fed admins: {len(db.fed_admins(fed_id))}\n"
        f"💬 Groups: {len(db.fed_chats(fed_id))}\n"
        f"🔨 Bans: {len(db.fed_banlist(fed_id))}",
        parse_mode=ParseMode.HTML)


async def joinfed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /joinfed <fed_id>")
    fed_id = context.args[0].strip()
    fed = db.get_fed(fed_id)
    if not fed:
        return await update.effective_message.reply_text("❌ এমন Fed ID পাওয়া যায়নি।")
    db.link_chat_fed(update.effective_chat.id, fed_id)
    await update.effective_message.reply_text(
        f"✅ গ্রুপ <b>{html_escape(fed['name'])}</b> federation-এ যুক্ত হয়েছে!",
        parse_mode=ParseMode.HTML)


async def leavefed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    if not db.get_chat_fed(update.effective_chat.id):
        return await update.effective_message.reply_text("❌ এই গ্রুপ কোনো federation-এ যুক্ত না।")
    db.unlink_chat_fed(update.effective_chat.id)
    await update.effective_message.reply_text("✅ Federation থেকে বেরিয়ে গেছেন।")


async def fban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = await _require_fed_admin(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    target_id, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    fed = db.get_fed(fed_id)
    if target_id == user.id or target_id == fed["owner_id"]:
        return await update.effective_message.reply_text("❌ নিজেকে বা fed owner-কে fban করা যাবে না।")
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    db.fban_user(fed_id, target_id, reason, user.id)
    ok, failed = await fanout_ban(context.bot, fed_id, target_id, ban=True)
    await update.effective_message.reply_text(
        f"🔨 <b>Fed-ban!</b>\n👤 <code>{target_id}</code>\n"
        f"📝 কারণ: {html_escape(reason) or '—'}\n"
        f"✅ {ok} গ্রুপে ব্যান{'' if not failed else f', ❌ {failed}টিতে ব্যর্থ'}",
        parse_mode=ParseMode.HTML)


async def unfban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = await _require_fed_admin(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    target_id, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    if not db.is_fed_banned(fed_id, target_id):
        return await update.effective_message.reply_text("❌ এই ইউজার fed-ban তালিকায় নেই।")
    db.unfban_user(fed_id, target_id)
    ok, failed = await fanout_ban(context.bot, fed_id, target_id, ban=False)
    await update.effective_message.reply_text(
        f"✅ <b>Fed-unban!</b> 👤 <code>{target_id}</code>\n"
        f"{ok} গ্রুপে আনব্যান{'' if not failed else f', ❌ {failed}টিতে ব্যর্থ'}",
        parse_mode=ParseMode.HTML)


async def fedbanlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = await _require_fed_admin(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    rows = db.fed_banlist(fed_id)
    if not rows:
        return await update.effective_message.reply_text("📭 Fed-ban তালিকা খালি।")
    lines = [f"🔨 <b>Fed bans ({len(rows)}):</b>"]
    for r in rows[:100]:
        reason = f" — {html_escape(r['reason'])}" if r["reason"] else ""
        lines.append(f'• <a href="tg://user?id={r["user_id"]}">{r["user_id"]}</a>{reason}')
    if len(rows) > 100:
        lines.append(f"…আরও {len(rows) - 100}টি")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def fedpromote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = _resolve_fed(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    fed = db.get_fed(fed_id)
    if not fed or fed["owner_id"] != user.id:
        return await update.effective_message.reply_text("❌ শুধু fed owner promote করতে পারেন।")
    target_id, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    db.fed_promote(fed_id, target_id)
    await update.effective_message.reply_text(f"✅ <code>{target_id}</code> এখন fed admin।", parse_mode=ParseMode.HTML)


async def feddemote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fed_id, err = _resolve_fed(update, user.id)
    if err:
        return await clean_reply(update, context, err)
    fed = db.get_fed(fed_id)
    if not fed or fed["owner_id"] != user.id:
        return await update.effective_message.reply_text("❌ শুধু fed owner demote করতে পারেন।")
    target_id, terr = await get_target_user(update, context)
    if terr:
        return await update.effective_message.reply_text(terr)
    if target_id == fed["owner_id"]:
        return await update.effective_message.reply_text("❌ Owner-কে demote করা যাবে না।")
    if db.fed_demote(fed_id, target_id):
        await update.effective_message.reply_text(f"✅ <code>{target_id}</code> আর fed admin না।", parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text("❌ এই ইউজার fed admin না।")


# ------------------------------------------------------- auto-enforce on join
async def fed_join_enforce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    chat = update.effective_chat
    if not result or chat.type == "private":
        return
    user = result.new_chat_member.user
    old = result.old_chat_member.status
    new = result.new_chat_member.status
    if not (old in ("left", "kicked") and new == "member"):
        return
    if user.is_bot:
        return
    fed_id = db.get_chat_fed(chat.id)
    if not fed_id or not db.is_fed_banned(fed_id, user.id):
        return
    try:
        await context.bot.ban_chat_member(chat.id, user.id)
        await context.bot.send_message(
            chat.id,
            f"🔨 Fed-banned ইউজার auto-ban: <code>{user.id}</code> ({html_escape(db.fed_ban_reason(fed_id, user.id)) or '—'})",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


def register(app):
    for cmd, fn in [
        ("newfed", newfed), ("delfed", delfed), ("fedinfo", fedinfo),
        ("joinfed", joinfed), ("leavefed", leavefed),
        ("fban", fban), ("unfban", unfban), ("fedbanlist", fedbanlist),
        ("fedpromote", fedpromote), ("feddemote", feddemote),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(ChatMemberHandler(fed_join_enforce, ChatMemberHandler.CHAT_MEMBER))
