"""Misc: /start /help /info /id /admins /afk /ping + AFK watcher.

/help shows an inline-button menu, one page per module.
AFK: /afk <reason> sets; any message from the user clears it;
     mentions/replies to an AFK user get an auto-notice.
"""

import time

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
from utils import check_admin, clean_reply, get_target_user, html_escape, is_user_admin, user_link

HELP_PAGES = {
    "admin": ("👮 <b>Admin</b>\n/ban, /tban &lt;5m|2h|1d|1w&gt;, /unban, /kick,\n"
              "/mute, /tmute &lt;সময়&gt;, /unmute,\n/promote, /demote,\n"
              "/pin, /unpin, /unpinall, /purge, /del,\n/announce, /announce pin\n"
              "<i>টার্গেট: রিপ্লাই / ID / @username</i>"),
    "warns": ("⚠️ <b>Warns</b>\n/warn, /unwarn, /warns, /resetwarns,\n"
              "/warnlimit &lt;n&gt;, /warnmode &lt;ban|mute|kick&gt;,\n"
              "/addwarn &lt;শব্দ&gt;, /nowarn, /warnfilters"),
    "filters": ("🔎 <b>Filters & Notes</b>\n/filter &lt;শব্দ&gt; &lt;উত্তর&gt;, /filters,\n"
                "/stop &lt;শব্দ&gt;, /stopall\n/save &lt;নাম&gt; &lt;টেক্সট&gt;, /get &lt;নাম&gt;,\n"
                "/#নাম, /notes, /clear &lt;নাম&gt;, /clearall,\n/privatenotes &lt;on|off&gt;\n"
                "<i>{first} {username} {chatname} + [label](url) বাটন সাপোর্ট করে</i>"),
    "welcome": ("👋 <b>Welcome / Goodbye / Rules</b>\n/setwelcome, /resetwelcome,\n"
                "/welcome &lt;on|off&gt;, /setgoodbye, /resetgoodbye,\n"
                "/goodbye &lt;on|off&gt;, /welcomemute &lt;on|off&gt;,\n"
                "/cleanwelcome &lt;on|off&gt;\n/setrules, /rules, /clearrules"),
    "locks": ("🔐 <b>Locks</b>\n/lock &lt;type&gt;, /unlock &lt;type&gt;,\n"
              "/locks, /locktypes\n<i>sticker, gif, media, photo, video, document,\n"
              "audio, voice, videonote, url, forward, contact,\nlocation, poll, game, rtl, button, inline, all</i>"),
    "flood": ("🌊 <b>Anti-flood</b>\n/setflood &lt;n&gt; (0=off), /flood,\n"
              "/setfloodmode &lt;ban|kick|mute|warn&gt;"),
    "blacklist": ("🚫 <b>Blacklist</b>\n/addblacklist &lt;শব্দ&gt;, /unblacklist,\n"
                  "/blacklist, /blacklistmode &lt;off|del|warn|ban|mute|kick&gt;,\n"
                  "/blsticker, /unblsticker, /blstickers"),
    "misc": ("ℹ️ <b>বিবিধ</b>\n/report (রিপ্লাই করে), /reports &lt;on|off&gt;,\n"
             "/info, /id, /admins, /afk &lt;কারণ&gt;, /ping"),
    "connect": ("🔗 <b>Connect</b>\n/connect, /disconnect\n"
                "<i>PM থেকে গ্রুপের কমান্ড চালান — গ্রুপে /connect দিন,\n"
                "তারপর PM-এ /announce, /setwelcome ইত্যাদি দিলে গ্রুপে কাজ করবে</i>"),
}

_start_time = time.time()


# ------------------------------------------------------------------ start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if update.effective_chat.type != "private":
        return await msg.reply_text("👋 আমি চালু আছি! সাহায্যের জন্য PM-এ /help দিন।")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Help", callback_data="help:menu"),
         InlineKeyboardButton("➕ গ্রুপে যোগ করুন",
                              url=f"https://t.me/{context.bot.username}?startgroup=true")],
    ])
    await msg.reply_text(
        "👋 <b>স্বাগতম!</b>\nআমি Rose-স্টাইল গ্রুপ ম্যানেজমেন্ট বট।\n\n"
        "আমাকে গ্রুপে অ্যাড করে অ্যাডমিন করুন, তারপর /help দিয়ে সব কমান্ড দেখুন।",
        parse_mode=ParseMode.HTML, reply_markup=kb)


# ------------------------------------------------------------------- help
def _help_menu_kb():
    rows = []
    keys = list(HELP_PAGES)
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(keys[i].capitalize(), callback_data=f"help:{keys[i]}")]
        if i + 1 < len(keys):
            row.append(InlineKeyboardButton(keys[i + 1].capitalize(), callback_data=f"help:{keys[i+1]}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📖 <b>Help মেনু</b> — মডিউল বেছে নিন:", parse_mode=ParseMode.HTML,
        reply_markup=_help_menu_kb())


async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key == "menu":
        return await query.edit_message_text(
            "📖 <b>Help মেনু</b> — মডিউল বেছে নিন:", parse_mode=ParseMode.HTML,
            reply_markup=_help_menu_kb())
    page = HELP_PAGES.get(key, "❌ পাওয়া যায়নি।")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="help:menu")]])
    await query.edit_message_text(page, parse_mode=ParseMode.HTML, reply_markup=kb)


# ------------------------------------------------------------------- info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        user = msg.reply_to_message.from_user
    elif context.args:
        target, terr = await get_target_user(update, context)
        if terr:
            return await msg.reply_text(terr)
        try:
            user = (await context.bot.get_chat(target)).to_dict()
            # get_chat returns Chat; build a simple namespace
            class _U: pass
            u = _U()
            u.id = target
            u.first_name = user.get("first_name", "")
            u.last_name = user.get("last_name")
            u.username = user.get("username")
            u.is_bot = user.get("is_bot", False)
            user = u
        except Exception:
            return await msg.reply_text("❌ ইউজার পাওয়া যায়নি।")
    else:
        user = msg.from_user
    text = (f"ℹ️ <b>User Info</b>\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 নাম: {html_escape(user.first_name or '')} {html_escape(user.last_name or '')}\n"
            f"🔗 ইউজারনেম: @{html_escape(user.username) if getattr(user, 'username', None) else '—'}\n"
            f"🤖 বট: {'হ্যাঁ' if getattr(user, 'is_bot', False) else 'না'}\n"
            f"🔗 লিংক: {user_link(user.id, user.first_name or 'user')}")
    await msg.reply_text(text, parse_mode=ParseMode.HTML)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    lines = [f"👤 আপনার ID: <code>{msg.from_user.id}</code>",
             f"💬 চ্যাট ID: <code>{msg.chat_id}</code>"]
    if msg.reply_to_message and msg.reply_to_message.from_user:
        lines.append(f"↩️ রিপ্লাই করা ইউজারের ID: <code>{msg.reply_to_message.from_user.id}</code>")
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        return await update.effective_message.reply_text("❌ শুধু গ্রুপে কাজ করে।")
    try:
        members = await chat.get_administrators()
    except Exception:
        return await update.effective_message.reply_text("❌ অ্যাডমিন তালিকা পাওয়া যায়নি।")
    owners = [m for m in members if m.status == ChatMemberStatus.OWNER]
    admins_ = [m for m in members if m.status == ChatMemberStatus.ADMINISTRATOR]
    lines = ["👑 <b>Owner:</b>"]
    lines += [f"• {user_link(m.user.id, m.user.first_name)}" for m in owners] or ["• —"]
    lines.append("\n🛡️ <b>Admins:</b>")
    lines += [f"• {user_link(m.user.id, m.user.first_name)}" for m in admins_] or ["• —"]
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# -------------------------------------------------------------------- afk
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) if context.args else "AFK"
    db.set_afk(update.effective_user.id, reason)
    await update.effective_message.reply_text(
        f"💤 {user_link(update.effective_user.id, update.effective_user.first_name)} এখন AFK: {html_escape(reason)}",
        parse_mode=ParseMode.HTML)


async def afk_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user or msg.text and msg.text.startswith("/afk"):
        return
    chat = update.effective_chat
    if chat.type == "private":
        return
    uid = msg.from_user.id
    # sender back -> clear AFK
    if db.get_afk(uid) is not None:
        db.clear_afk(uid)
        await msg.reply_text(
            f"👋 {user_link(uid, msg.from_user.first_name)} আবার ফিরে এসেছেন!",
            parse_mode=ParseMode.HTML)
        return
    # mentioned or replied-to user AFK?
    targets = set()
    if msg.reply_to_message and msg.reply_to_message.from_user:
        targets.add(msg.reply_to_message.from_user)
    for entity in msg.entities or []:
        if entity.type == "text_mention" and entity.user:
            targets.add(entity.user)
        elif entity.type == "mention":
            username = msg.text[entity.offset:entity.offset + entity.length].lstrip("@")
            try:
                c = await context.bot.get_chat("@" + username)
                class _U: pass
                u = _U()
                u.id, u.first_name = c.id, c.first_name or username
                targets.add(u)
            except Exception:
                pass
    for t in targets:
        reason = db.get_afk(t.id)
        if reason is not None:
            await msg.reply_text(
                f"💤 {user_link(t.id, t.first_name)} এখন AFK: {html_escape(reason)}",
                parse_mode=ParseMode.HTML)
            break


# ------------------------------------------------------------------- ping
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t0 = time.time()
    m = await update.effective_message.reply_text("🏓 Pong!")
    dt = (time.time() - t0) * 1000
    uptime = int(time.time() - _start_time)
    await m.edit_text(f"🏓 Pong! <code>{dt:.0f}ms</code>\n⏱️ Uptime: {uptime // 3600}h {(uptime % 3600) // 60}m",
                      parse_mode=ParseMode.HTML)


# ------------------------------------------------------------- botclean
async def botclean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-delete the bot's own reply messages after N seconds."""
    ok, err = await check_admin(update, context, need_delete=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args:
        cur = db.get_botclean_timer(chat_id)
        return await clean_reply(
            update, context,
            f"বর্তমান: {'off' if cur <= 0 else f'{cur} সেকেন্ড'}\n"
            "ব্যবহার: /botclean <সেকেন্ড|off>\nউদাহরণ: /botclean 30")
    arg = context.args[0].lower()
    if arg in ("off", "no", "0"):
        db.set_botclean_timer(chat_id, 0)
        return await clean_reply(update, context, "✅ Bot মেসেজ auto-clean বন্ধ।")
    try:
        secs = int(arg)
    except ValueError:
        return await clean_reply(
            update, context,
            "ব্যবহার: /botclean <সেকেন্ড|off>\nউদাহরণ: /botclean 30")
    if secs < 5 or secs > 86400:
        return await clean_reply(update, context, "⏱️ ৫ সেকেন্ড থেকে ২৪ ঘণ্টার মধ্যে দিন।")
    db.set_botclean_timer(chat_id, secs)
    await clean_reply(
        update, context,
        f"✅ এখন থেকে বটের reply মেসেজ {secs} সেকেন্ড পর auto-delete হবে।")


def register(app):
    for cmd, fn in [
        ("start", start), ("help", help_cmd), ("info", info), ("id", id_cmd),
        ("admins", admins), ("afk", afk), ("ping", ping),
        ("botclean", botclean_cmd),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(help_button, pattern=r"^help:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, afk_watcher), group=7)
