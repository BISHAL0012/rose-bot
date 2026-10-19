"""Anti-raid: auto-protect the group during join floods.

/raid <joins> <seconds>  - e.g. /raid 8 30  (8 joins in 30s -> raid mode)
/raid off                - disable
/raidstatus              - current settings

When triggered, raid mode lasts 10 minutes: every new joiner is muted
until it ends, and admins are notified.
"""

import time
from collections import defaultdict, deque

from telegram import Update
from telegram.ext import ChatMemberHandler, CommandHandler, ContextTypes

import database as db
from utils import MUTE_PERMISSIONS, UNMUTE_PERMISSIONS, check_admin, is_user_admin, clean_reply

RAID_DURATION = 600  # 10 minutes


class RaidTracker:
    """Pure join-rate logic (testable without Telegram)."""

    def __init__(self):
        self.joins = defaultdict(deque)   # chat_id -> deque[timestamps]
        self.raid_until = {}              # chat_id -> timestamp
        self.raid_muted = defaultdict(set)  # chat_id -> set[user_id]

    def add_join(self, chat_id: int, joins_limit: int, window: int, now: float) -> str:
        """'triggered' on first breach, 'raid' while active, else 'ok'."""
        if self.raid_until.get(chat_id, 0) > now:
            return "raid"
        dq = self.joins[chat_id]
        dq.append(now)
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= joins_limit:
            self.raid_until[chat_id] = now + RAID_DURATION
            dq.clear()
            return "triggered"
        return "ok"

    def in_raid(self, chat_id: int, now: float) -> bool:
        return self.raid_until.get(chat_id, 0) > now

    def end_raid(self, chat_id: int):
        muted = self.raid_muted.pop(chat_id, set())
        self.raid_until.pop(chat_id, None)
        return muted


_tracker = RaidTracker()


async def _end_raid_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    for uid in _tracker.end_raid(chat_id):
        try:
            await context.bot.restrict_chat_member(chat_id, uid, UNMUTE_PERMISSIONS)
        except Exception:
            pass
    try:
        await context.bot.send_message(chat_id, "✅ Raid mode শেষ — নতুন join-রা আবার স্বাভাবিক।")
    except Exception:
        pass


# ------------------------------------------------------------------ commands
async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context, need_restrict=True)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args:
        j, s = db.get_raid(chat_id)
        return await update.effective_message.reply_text(
            f"🛡️ Raid protection: {'off' if j == 0 else f'{j} joins / {s}s'}\n"
            "ব্যবহার: /raid <joins> <seconds>  |  /raid off\n"
            "উদাহরণ: /raid 8 30")
    if context.args[0].lower() in ("off", "no", "0"):
        db.disable_raid(chat_id)
        _tracker.raid_until.pop(chat_id, None)
        return await update.effective_message.reply_text("✅ Raid protection বন্ধ।")
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        return await update.effective_message.reply_text(
            "ব্যবহার: /raid <joins> <seconds>\nউদাহরণ: /raid 8 30")
    joins, seconds = int(context.args[0]), int(context.args[1])
    if joins < 3 or joins > 100 or seconds < 10 or seconds > 3600:
        return await update.effective_message.reply_text(
            "❌ joins: ৩–১০০, seconds: ১০–৩৬০০ এর মধ্যে দিন।")
    db.set_raid(chat_id, joins, seconds)
    await update.effective_message.reply_text(
        f"✅ Raid protection চালু: {seconds} সেকেন্ডে {joins} join হলে ১০ মিনিটের raid mode।")


async def raidstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    j, s = db.get_raid(chat_id)
    active = _tracker.in_raid(chat_id, time.time())
    await update.effective_message.reply_text(
        f"🛡️ Raid protection: {'off' if j == 0 else f'{j} joins / {s}s'}\n"
        f"Raid mode: {'🔴 চালু' if active else '🟢 বন্ধ'}")


# ------------------------------------------------------------------- watcher
async def raid_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    chat = update.effective_chat
    if not result or chat.type == "private":
        return
    user = result.new_chat_member.user
    old = result.old_chat_member.status
    new = result.new_chat_member.status
    joined = old in ("left", "kicked") and new == "member"
    if not joined or user.is_bot:
        return
    chat_id = chat.id
    joins, seconds = db.get_raid(chat_id)
    if joins <= 0:
        return
    if await is_user_admin(chat, user.id):
        return

    now = time.time()
    state = _tracker.add_join(chat_id, joins, seconds, now)
    if state == "ok":
        return
    # raid active (newly triggered or ongoing): mute the joiner
    try:
        await chat.restrict_member(user.id, MUTE_PERMISSIONS)
        _tracker.raid_muted[chat_id].add(user.id)
    except Exception:
        pass
    if state == "triggered":
        try:
            await context.bot.send_message(
                chat_id,
                "🚨 <b>Raid mode চালু!</b> পরের ১০ মিনিট নতুন join-রা mute থাকবে।",
                parse_mode="HTML")
        except Exception:
            pass
        if context.job_queue:
            context.job_queue.run_once(
                _end_raid_job, RAID_DURATION, data=chat_id,
                name=f"raidend_{chat_id}")


def register(app):
    app.add_handler(CommandHandler("raid", raid))
    app.add_handler(CommandHandler("raidstatus", raidstatus))
    app.add_handler(ChatMemberHandler(raid_watcher, ChatMemberHandler.CHAT_MEMBER))
