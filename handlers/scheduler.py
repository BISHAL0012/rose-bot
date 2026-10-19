"""Scheduled announcements: daily messages at fixed Asia/Dhaka times.

/schedule <HH:MM> <message>  - every day at HH:MM (24h, Dhaka time)
/schedules                   - list with ids
/unschedule <id>             - remove one
"""

import datetime
import re
from datetime import timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

import database as db
from utils import check_admin, command_text, extract_buttons, clean_reply

DHAKA = timezone(timedelta(hours=6))  # Asia/Dhaka (no DST)
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_hhmm(s: str):
    """Pure: 'HH:MM' -> (hh, mm) or None."""
    m = _HHMM_RE.match((s or "").strip())
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def _job_name(sched_id: int) -> str:
    return f"sched_{sched_id}"


async def _send_scheduled(context: ContextTypes.DEFAULT_TYPE):
    chat_id, text = context.job.data
    clean, markup = extract_buttons(text)
    try:
        await context.bot.send_message(
            chat_id, f"📢 {clean}", parse_mode=ParseMode.HTML,
            reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


def arm_schedule(context: ContextTypes.DEFAULT_TYPE, sched_id: int,
                 chat_id: int, time_hhmm: str, text: str) -> bool:
    parsed = parse_hhmm(time_hhmm)
    if not parsed or not context.job_queue:
        return False
    hh, mm = parsed
    context.job_queue.run_daily(
        _send_scheduled,
        datetime.time(hh, mm, tzinfo=DHAKA),
        data=(chat_id, text),
        name=_job_name(sched_id),
    )
    return True


def unschedule_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not context.job_queue:
        return
    for job in context.job_queue.jobs():
        try:
            if job.name.startswith("sched_") and job.data[0] == chat_id:
                job.schedule_removal()
        except Exception:
            pass


def reschedule_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> int:
    n = 0
    for row in db.list_schedules(chat_id):
        if arm_schedule(context, row["id"], chat_id, row["time_hhmm"], row["text"]):
            n += 1
    return n


def reschedule_all(app) -> int:
    """Called once at startup (post_init): re-arm every saved schedule."""
    n = 0

    class _Ctx:
        def __init__(self, jq):
            self.job_queue = jq

    context = _Ctx(app.job_queue)
    for row in db.list_all_schedules():
        if arm_schedule(context, row["id"], row["chat_id"], row["time_hhmm"], row["text"]):
            n += 1
    return n


# ------------------------------------------------------------------ commands
async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or not parse_hhmm(context.args[0]):
        return await update.effective_message.reply_text(
            "ব্যবহার: /schedule <HH:MM> <মেসেজ>\n"
            "উদাহরণ: /schedule 21:00 আজ রাত ৯টায় লাইভ! [🎯 Join](https://t.me/x|red)\n"
            "সময়: ২৪ ঘণ্টা, ঢাকা টাইম।")
    time_hhmm = context.args[0]
    text = command_text(update).split(None, 1)
    text = text[1] if len(text) > 1 else ""
    if not text:
        return await update.effective_message.reply_text("❌ মেসেজ লিখুন: /schedule <HH:MM> <মেসেজ>")
    sched_id = db.add_schedule(chat_id, time_hhmm, text)
    arm_schedule(context, sched_id, chat_id, time_hhmm, text)
    await update.effective_message.reply_text(
        f"✅ প্রতিদিন {time_hhmm} (ঢাকা) টায় পাঠানো হবে। ID: {sched_id}")


async def schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    rows = db.list_schedules(update.effective_chat.id)
    if not rows:
        return await update.effective_message.reply_text("📭 কোনো schedule নেই।")
    lines = ["⏰ <b>Schedules:</b>"]
    for r in rows:
        preview = (r["text"][:60] + "…") if len(r["text"]) > 60 else r["text"]
        lines.append(f"• <code>{r['id']}</code> — {r['time_hhmm']}: {preview}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def unschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("ব্যবহার: /unschedule <id>")
    row = db.get_schedule(int(context.args[0]))
    if not row or row["chat_id"] != chat_id:
        return await update.effective_message.reply_text("❌ এই গ্রুপে এমন ID নেই।")
    db.delete_schedule(row["id"])
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name == _job_name(row["id"]):
                job.schedule_removal()
    await update.effective_message.reply_text(f"✅ Schedule {row['id']} মুছে ফেলা হয়েছে।")


def register(app):
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("schedules", schedules))
    app.add_handler(CommandHandler("unschedule", unschedule))
