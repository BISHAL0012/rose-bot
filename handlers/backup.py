"""Backup: /export group settings to JSON, /import to restore.

/export  - send all settings as a .json document (admin)
/import  - reply to the JSON file to restore (admin)
"""

import json
import os
import tempfile

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import database as db
from utils import check_admin, clean_reply

BACKUP_VERSION = 5


def build_export(chat_id: int) -> dict:
    """Pure (DB-only): snapshot every per-chat setting into a dict."""
    data = {"backup_version": BACKUP_VERSION, "chat_id": chat_id}
    data["locks"] = db.list_locks(chat_id)
    data["warn_limit"] = db.get_warn_limit(chat_id)
    data["warn_mode"] = db.get_warn_mode(chat_id)
    data["warn_filters"] = db.list_warn_filters(chat_id)
    data["filters"] = {k: db.get_filter(chat_id, k) for k in db.list_filters(chat_id)}
    data["notes"] = {n: db.get_note(chat_id, n) for n in db.list_notes(chat_id)}
    data["blacklist"] = db.list_blacklist(chat_id)
    data["blacklist_mode"] = db.get_blacklist_mode(chat_id)
    data["flood_limit"] = db.get_flood_limit(chat_id)
    data["flood_mode"] = db.get_flood_mode(chat_id)
    data["welcome_text"], data["welcome_on"] = db.get_welcome(chat_id)
    data["goodbye_text"], data["goodbye_on"] = db.get_goodbye(chat_id)
    data["welcome_timer"] = db.get_welcome_timer(chat_id)
    data["goodbye_timer"] = db.get_goodbye_timer(chat_id)
    data["welcomemute"] = db.get_welcomemute(chat_id)
    data["cleanwelcome"] = db.get_cleanwelcome(chat_id)
    data["welcome_media"] = db.get_welcome_media(chat_id)
    data["rules"] = db.get_rules(chat_id)
    data["reports"] = db.get_reports(chat_id)
    j, s = db.get_raid(chat_id)
    data["raid"] = {"joins": j, "seconds": s}
    data["schedules"] = [
        {"time_hhmm": r["time_hhmm"], "text": r["text"]}
        for r in db.list_schedules(chat_id)
    ]
    data["slowmode"] = db.get_slowmode(chat_id)
    data["chat_fed"] = db.get_chat_fed(chat_id)
    return data


def apply_import(chat_id: int, data: dict) -> None:
    """Pure (DB-only): validate + restore an export dict. Raises ValueError."""
    if not isinstance(data, dict) or data.get("backup_version") != BACKUP_VERSION:
        raise ValueError("❌ এই backup ফাইল সাপোর্টেড না (version mismatch)।")

    for lock in db.list_locks(chat_id):
        db.set_lock(chat_id, lock, False)
    for lock in data.get("locks", []):
        db.set_lock(chat_id, lock, True)

    db.set_warn_limit(chat_id, int(data.get("warn_limit", 3)))
    db.set_warn_mode(chat_id, data.get("warn_mode", "ban"))
    for kw in db.list_warn_filters(chat_id):
        db.remove_warn_filter(chat_id, kw)
    for kw in data.get("warn_filters", []):
        db.add_warn_filter(chat_id, kw)

    db.delete_all_filters(chat_id)
    for kw, reply in (data.get("filters") or {}).items():
        db.save_filter(chat_id, kw, reply)
    db.delete_all_notes(chat_id)
    for name, reply in (data.get("notes") or {}).items():
        db.save_note(chat_id, name, reply)

    db.clear_blacklist(chat_id)
    for w in data.get("blacklist", []):
        db.add_blacklist(chat_id, w)
    db.set_blacklist_mode(chat_id, data.get("blacklist_mode", "del"))
    db.set_flood_limit(chat_id, int(data.get("flood_limit", 0)))
    db.set_flood_mode(chat_id, data.get("flood_mode", "mute"))

    db.set_welcome(chat_id, data.get("welcome_text", db.DEFAULT_WELCOME))
    db.set_welcome_on(chat_id, bool(data.get("welcome_on", True)))
    db.set_goodbye(chat_id, data.get("goodbye_text", db.DEFAULT_GOODBYE))
    db.set_goodbye_on(chat_id, bool(data.get("goodbye_on", True)))
    db.set_welcome_timer(chat_id, int(data.get("welcome_timer", 0)))
    db.set_goodbye_timer(chat_id, int(data.get("goodbye_timer", 0)))
    db.set_welcomemute(chat_id, bool(data.get("welcomemute", False)))
    db.set_cleanwelcome(chat_id, bool(data.get("cleanwelcome", False)))
    if data.get("welcome_media"):
        db.set_welcome_media(chat_id, data["welcome_media"])
    else:
        db.clear_welcome_media(chat_id)
    db.set_rules(chat_id, data.get("rules", ""))
    db.set_reports(chat_id, bool(data.get("reports", True)))

    raid = data.get("raid") or {}
    if raid.get("joins"):
        db.set_raid(chat_id, int(raid["joins"]), int(raid["seconds"]))
    else:
        db.disable_raid(chat_id)

    for s in db.list_schedules(chat_id):
        db.delete_schedule(s["id"])
    for s in data.get("schedules", []):
        if s.get("time_hhmm"):
            db.add_schedule(chat_id, s["time_hhmm"], s.get("text", ""))

    db.set_slowmode(chat_id, int(data.get("slowmode", 0)))

    if data.get("chat_fed"):
        db.link_chat_fed(chat_id, data["chat_fed"])
    else:
        db.unlink_chat_fed(chat_id)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    chat_id = update.effective_chat.id
    data = build_export(chat_id)
    path = os.path.join(tempfile.gettempdir(), f"rose_backup_{chat_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(path, "rb") as f:
        await context.bot.send_document(
            chat_id, f, filename=f"rose_backup_{abs(chat_id)}.json",
            caption="💾 গ্রুপ সেটিংস ব্যাকআপ (v5)। /import দিয়ে রিস্টোর করুন।")
    try:
        os.remove(path)
    except OSError:
        pass


async def import_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, err = await check_admin(update, context)
    if not ok:
        return await clean_reply(update, context, err)
    msg = update.effective_message
    reply = msg.reply_to_message
    if not reply or not reply.document:
        return await msg.reply_text(
            "❌ ব্যাকআপ JSON ফাইলে রিপ্লাই করে /import দিন।")
    doc = reply.document
    if not (doc.file_name or "").endswith(".json"):
        return await msg.reply_text("❌ এটা JSON ব্যাকআপ ফাইল না।")
    path = os.path.join(tempfile.gettempdir(), f"rose_import_{update.effective_chat.id}.json")
    tg_file = await doc.get_file()
    await tg_file.download_to_drive(path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        apply_import(update.effective_chat.id, data)
    except ValueError as e:
        return await msg.reply_text(str(e))
    except Exception:
        return await msg.reply_text("❌ ফাইল পড়া যায়নি — সঠিক ব্যাকআপ ফাইল দিন।")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    # re-arm scheduled announcements from the restored data
    from handlers import scheduler
    scheduler.unschedule_chat(context, update.effective_chat.id)
    scheduler.reschedule_chat(context, update.effective_chat.id)
    await msg.reply_text("✅ ব্যাকআপ রিস্টোর হয়েছে!")


def register(app):
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("import", import_cmd))
