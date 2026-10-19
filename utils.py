"""Shared helpers: time parsing, admin checks, user resolution, formatting."""

import asyncio
import html
import re
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes

import database as db

# Permissions used for a proper mute: user can do nothing.
MUTE_PERMISSIONS = ChatPermissions(can_send_messages=False)

# Full permissions used to unmute someone.
UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_other_messages=True,
    can_send_polls=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)

_TIME_RE = re.compile(r"^(\d+)\s*([mhdw])$", re.IGNORECASE)
_BUTTON_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# color name -> Bot API 9.4 style
_COLOR_MAP = {
    "red": "danger", "danger": "danger",
    "blue": "primary", "primary": "primary",
    "green": "success", "success": "success",
}


def parse_time(timestr: str):
    """Parse '5m'/'2h'/'1d'/'1w' -> timezone-aware datetime (until_date), or None."""
    m = _TIME_RE.match((timestr or "").strip())
    if not m:
        return None
    amount, unit = int(m.group(1)), m.group(2).lower()
    delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
             "d": timedelta(days=amount), "w": timedelta(weeks=amount)}[unit]
    return datetime.now(timezone.utc) + delta


async def issuer_is_admin(update, context) -> bool:
    """True if the command issuer is an admin/owner of the chat."""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return True
    try:
        member = await chat.get_member(user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def bot_member(update, context):
    """Return the bot's ChatMember object for this chat (or None)."""
    chat = update.effective_chat
    try:
        return await chat.get_member(context.bot.id)
    except Exception:
        return None


async def check_admin(update, context, need_restrict=False, need_delete=False,
                      need_pin=False, need_promote=False):
    """Verify issuer is admin AND bot has needed rights.

    Returns (ok: bool, error_message: str|None).
    """
    chat = update.effective_chat
    if chat.type == "private":
        if not db.get_connection(update.effective_user.id):
            return False, ("❌ PM-এ এই কমান্ড ব্যবহার করতে আগে গ্রুপে গিয়ে "
                           "/connect দিন।")
        return False, "❌ এই কমান্ড শুধু গ্রুপে কাজ করে।"

    if not await issuer_is_admin(update, context):
        return False, "❌ শুধু অ্যাডমিনরা এই কমান্ড ব্যবহার করতে পারেন।"

    bm = await bot_member(update, context)
    if not bm or bm.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return False, "❌ আমাকে (বটকে) প্রথমে গ্রুপের অ্যাডমিন করুন।"

    missing = []
    if need_restrict and not getattr(bm, "can_restrict_members", False):
        missing.append("ban/restrict users")
    if need_delete and not getattr(bm, "can_delete_messages", False):
        missing.append("delete messages")
    if need_pin and not getattr(bm, "can_pin_messages", False):
        missing.append("pin messages")
    if need_promote and not getattr(bm, "can_promote_members", False):
        missing.append("promote members")
    if missing:
        return False, "❌ বটের এই পারমিশন নেই: " + ", ".join(missing) + "। বটকে পারমিশন দিন।"
    return True, None


async def get_target_user(update, context):
    """Resolve target user from reply, user-id, or @username.

    Returns (user_id|None, error_message|None).
    """
    msg = update.effective_message
    # 1) replied message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id, None
    # 2) argument: numeric id or @username
    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            return int(arg), None
        try:
            chat = await context.bot.get_chat("@" + arg)
            return chat.id, None
        except Exception:
            return None, "❌ ইউজার পাওয়া যায়নি। রিপ্লাই করুন, অথবা সঠিক ID/@username দিন।"
    return None, "❌ কাকে? মেসেজে রিপ্লাই করুন অথবা ID/@username দিন।"


def mention_html(user: User) -> str:
    name = html.escape(user.first_name or "user")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def user_link(user_id: int, name: str = "user") -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def fill_placeholders(text: str, user: User, chat, count: int = 0) -> str:
    """Fill {first} {last} {fullname} {name} {username} {id} {chatname} {count}."""
    first = user.first_name or ""
    last = user.last_name or ""
    username = f"@{user.username}" if user.username else first
    return (
        text.replace("{first}", first)
        .replace("{last}", last)
        .replace("{fullname}", f"{first} {last}".strip())
        .replace("{name}", f"{first} {last}".strip())
        .replace("{username}", username)
        .replace("{id}", str(user.id))
        .replace("{chatname}", getattr(chat, "title", "") or "")
        .replace("{count}", str(count))
    )


def extract_buttons(text: str):
    """Parse [label](url) or [label](url|color) syntax -> (clean_text, InlineKeyboardMarkup|None).

    color: red/danger, blue/primary, green/success (Bot API 9.4 style).
    Example: [Join Now](https://t.me/x|red)
    """
    buttons = []

    def _repl(m):
        label, url = m.group(1).strip(), m.group(2).strip()
        if url.startswith("buttonurl:"):
            url = url.split("buttonurl:", 1)[1]
        style = None
        if "|" in url:
            url, color = url.rsplit("|", 1)
            url = url.strip()
            style = _COLOR_MAP.get(color.strip().lower())
        kwargs = {"url": url}
        if style:
            kwargs["style"] = style
        buttons.append(InlineKeyboardButton(label, **kwargs))
        return ""

    clean = _BUTTON_RE.sub(_repl, text).strip()
    if not buttons:
        return text, None
    # one button per row
    markup = InlineKeyboardMarkup([[b] for b in buttons])
    return clean, markup


def html_escape(text: str) -> str:
    return html.escape(text or "")


def command_text(update) -> str:
    """Return the raw text after the command, preserving line breaks.

    Unlike " ".join(context.args), this keeps newlines so multi-line
    welcome/rules messages stay formatted.
    """
    msg = update.effective_message
    text = msg.text or msg.caption or ""
    parts = text.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


async def safe_delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _botclean_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback: delete the bot's own reply message."""
    chat_id, msg_id = context.job.data
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


async def _botclean_fallback(bot, chat_id: int, msg_id: int, delay: int):
    """Fallback when job_queue is not available."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def _schedule_botclean(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                       msg_id: int, delay: int) -> None:
    if getattr(context, "job_queue", None):
        context.job_queue.run_once(
            _botclean_job, delay,
            data=(chat_id, msg_id),
            name=f"botclean_{chat_id}_{msg_id}")
    else:
        asyncio.create_task(_botclean_fallback(context.bot, chat_id, msg_id, delay))


async def clean_reply(update, context, text, **kwargs):
    """Reply to the command message and auto-delete the bot's reply after the
    chat's /botclean timer (0 = off). Returns the sent message."""
    msg = await update.effective_message.reply_text(text, **kwargs)
    try:
        secs = db.get_botclean_timer(update.effective_chat.id)
    except Exception:
        secs = 0
    if secs > 0:
        _schedule_botclean(context, update.effective_chat.id, msg.message_id, secs)
    return msg


async def is_user_admin(chat, user_id: int) -> bool:
    try:
        m = await chat.get_member(user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False
