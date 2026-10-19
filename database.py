"""SQLite persistence layer for the Rose-style group management bot.

All chat settings, warns, filters, notes, locks, etc. are stored here so
nothing is lost when the bot restarts. Thread-safe via a re-entrant lock.
Runtime DB lives at <package>/data.db (created on first run).
"""

import os
import sqlite3
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# FadeHost: persistent disk is /data (code dir is wiped on every deploy).
# Local/Termux: falls back to the package dir.
DATA_DIR = "/data" if os.path.isdir("/data") else BASE_DIR
DB_PATH = os.path.join(DATA_DIR, "data.db")

_LOCK = threading.RLock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist yet."""
    os.makedirs(BASE_DIR, exist_ok=True)
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER NOT NULL,
                key     TEXT    NOT NULL,
                value   TEXT    NOT NULL DEFAULT '',
                PRIMARY KEY (chat_id, key)
            );
            CREATE TABLE IF NOT EXISTS warns (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS warn_filters (
                chat_id INTEGER NOT NULL,
                keyword TEXT    NOT NULL,
                PRIMARY KEY (chat_id, keyword)
            );
            CREATE TABLE IF NOT EXISTS filters (
                chat_id INTEGER NOT NULL,
                keyword TEXT    NOT NULL,
                reply   TEXT    NOT NULL,
                PRIMARY KEY (chat_id, keyword)
            );
            CREATE TABLE IF NOT EXISTS notes (
                chat_id INTEGER NOT NULL,
                name    TEXT    NOT NULL,
                reply   TEXT    NOT NULL,
                PRIMARY KEY (chat_id, name)
            );
            CREATE TABLE IF NOT EXISTS blacklist (
                chat_id INTEGER NOT NULL,
                word    TEXT    NOT NULL,
                PRIMARY KEY (chat_id, word)
            );
            CREATE TABLE IF NOT EXISTS blstickers (
                chat_id INTEGER NOT NULL,
                file_id TEXT    NOT NULL,
                PRIMARY KEY (chat_id, file_id)
            );
            CREATE TABLE IF NOT EXISTS locks (
                chat_id   INTEGER NOT NULL,
                lock_type TEXT    NOT NULL,
                PRIMARY KEY (chat_id, lock_type)
            );
            CREATE TABLE IF NOT EXISTS pending_captcha (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                expires INTEGER NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS afk (
                user_id INTEGER PRIMARY KEY,
                reason  TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS connections (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS known_chats (
                chat_id INTEGER PRIMARY KEY,
                title   TEXT NOT NULL DEFAULT '',
                type    TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS members (
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                name      TEXT    NOT NULL DEFAULT '',
                last_seen INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS raid_settings (
                chat_id INTEGER PRIMARY KEY,
                joins   INTEGER NOT NULL DEFAULT 0,
                seconds INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS welcome_media (
                chat_id INTEGER PRIMARY KEY,
                file_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   INTEGER NOT NULL,
                time_hhmm TEXT    NOT NULL,
                text      TEXT    NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS slowmode (
                chat_id INTEGER PRIMARY KEY,
                seconds INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS feds (
                fed_id   TEXT PRIMARY KEY,
                name     TEXT NOT NULL DEFAULT '',
                owner_id INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS fed_chats (
                fed_id  TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                PRIMARY KEY (fed_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS fed_admins (
                fed_id  TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (fed_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS fed_bans (
                fed_id    TEXT NOT NULL,
                user_id   INTEGER NOT NULL,
                reason    TEXT NOT NULL DEFAULT '',
                banned_by INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (fed_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS chat_fed (
                chat_id INTEGER PRIMARY KEY,
                fed_id  TEXT NOT NULL DEFAULT ''
            );
            """
        )


# ---------------------------------------------------------------- generic kv
def get_setting(chat_id: int, key: str, default: str = "") -> str:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE chat_id=? AND key=?", (chat_id, key)
        ).fetchone()
        return row["value"] if row else default


def set_setting(chat_id: int, key: str, value) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO settings (chat_id, key, value) VALUES (?,?,?) "
            "ON CONFLICT(chat_id, key) DO UPDATE SET value=excluded.value",
            (chat_id, str(key), str(value)),
        )


def get_bool(chat_id: int, key: str, default: bool = False) -> bool:
    return get_setting(chat_id, key, "1" if default else "0") == "1"


def set_bool(chat_id: int, key: str, value: bool) -> None:
    set_setting(chat_id, key, "1" if value else "0")


def get_int(chat_id: int, key: str, default: int = 0) -> int:
    try:
        return int(get_setting(chat_id, key, str(default)))
    except ValueError:
        return default


# --------------------------------------------------------------------- warns
def get_warns(chat_id: int, user_id: int) -> int:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return row["count"] if row else 0


def add_warn(chat_id: int, user_id: int) -> int:
    """Increment warn count, return new total."""
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO warns (chat_id, user_id, count) VALUES (?,?,1) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET count=count+1",
            (chat_id, user_id),
        )
        row = conn.execute(
            "SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return row["count"]


def remove_warn(chat_id: int, user_id: int) -> int:
    """Decrement warn count (floor 0), return new total."""
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE warns SET count=CASE WHEN count>0 THEN count-1 ELSE 0 END "
            "WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        row = conn.execute(
            "SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return row["count"] if row else 0


def reset_warns(chat_id: int, user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))


def get_warn_limit(chat_id: int) -> int:
    return get_int(chat_id, "warn_limit", 3)


def set_warn_limit(chat_id: int, n: int) -> None:
    set_setting(chat_id, "warn_limit", n)


def get_warn_mode(chat_id: int) -> str:
    return get_setting(chat_id, "warn_mode", "ban")


def set_warn_mode(chat_id: int, mode: str) -> None:
    set_setting(chat_id, "warn_mode", mode)


def add_warn_filter(chat_id: int, keyword: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO warn_filters (chat_id, keyword) VALUES (?,?)",
            (chat_id, keyword.lower()),
        )


def remove_warn_filter(chat_id: int, keyword: str) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM warn_filters WHERE chat_id=? AND keyword=?",
            (chat_id, keyword.lower()),
        )
        return cur.rowcount > 0


def list_warn_filters(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT keyword FROM warn_filters WHERE chat_id=? ORDER BY keyword", (chat_id,)
        ).fetchall()
        return [r["keyword"] for r in rows]


# -------------------------------------------------------------------- filters
def save_filter(chat_id: int, keyword: str, reply: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO filters (chat_id, keyword, reply) VALUES (?,?,?) "
            "ON CONFLICT(chat_id, keyword) DO UPDATE SET reply=excluded.reply",
            (chat_id, keyword.lower(), reply),
        )


def get_filter(chat_id: int, keyword: str):
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT reply FROM filters WHERE chat_id=? AND keyword=?",
            (chat_id, keyword.lower()),
        ).fetchone()
        return row["reply"] if row else None


def list_filters(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT keyword FROM filters WHERE chat_id=? ORDER BY keyword", (chat_id,)
        ).fetchall()
        return [r["keyword"] for r in rows]


def delete_filter(chat_id: int, keyword: str) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM filters WHERE chat_id=? AND keyword=?", (chat_id, keyword.lower())
        )
        return cur.rowcount > 0


def delete_all_filters(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM filters WHERE chat_id=?", (chat_id,))


# ---------------------------------------------------------------------- notes
def save_note(chat_id: int, name: str, reply: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO notes (chat_id, name, reply) VALUES (?,?,?) "
            "ON CONFLICT(chat_id, name) DO UPDATE SET reply=excluded.reply",
            (chat_id, name.lower(), reply),
        )


def get_note(chat_id: int, name: str):
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT reply FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower())
        ).fetchone()
        return row["reply"] if row else None


def list_notes(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM notes WHERE chat_id=? ORDER BY name", (chat_id,)
        ).fetchall()
        return [r["name"] for r in rows]


def delete_note(chat_id: int, name: str) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower())
        )
        return cur.rowcount > 0


def delete_all_notes(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM notes WHERE chat_id=?", (chat_id,))


def get_privatenotes(chat_id: int) -> bool:
    return get_bool(chat_id, "privatenotes", False)


def set_privatenotes(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "privatenotes", on)


# ------------------------------------------------------------ welcome/goodbye
DEFAULT_WELCOME = "👋 স্বাগতম {first}!\n{chatname} গ্রুপে যোগ দেওয়ার জন্য ধন্যবাদ।"
DEFAULT_GOODBYE = "👋 {first} গ্রুপ ছেড়ে চলে গেছেন।"


def get_welcome(chat_id: int):
    return get_setting(chat_id, "welcome_text", DEFAULT_WELCOME), get_bool(chat_id, "welcome_on", True)


def set_welcome(chat_id: int, text: str) -> None:
    set_setting(chat_id, "welcome_text", text)


def set_welcome_on(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "welcome_on", on)


def reset_welcome(chat_id: int) -> None:
    set_setting(chat_id, "welcome_text", DEFAULT_WELCOME)


def get_goodbye(chat_id: int):
    return get_setting(chat_id, "goodbye_text", DEFAULT_GOODBYE), get_bool(chat_id, "goodbye_on", True)


def set_goodbye(chat_id: int, text: str) -> None:
    set_setting(chat_id, "goodbye_text", text)


def set_goodbye_on(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "goodbye_on", on)


def reset_goodbye(chat_id: int) -> None:
    set_setting(chat_id, "goodbye_text", DEFAULT_GOODBYE)


def get_welcomemute(chat_id: int) -> bool:
    return get_bool(chat_id, "welcomemute", False)


def set_welcomemute(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "welcomemute", on)


def get_cleanwelcome(chat_id: int) -> bool:
    return get_bool(chat_id, "cleanwelcome", False)


def set_cleanwelcome(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "cleanwelcome", on)


def get_last_welcome_msg(chat_id: int) -> int:
    return get_int(chat_id, "last_welcome_msg", 0)


def set_last_welcome_msg(chat_id: int, msg_id: int) -> None:
    set_setting(chat_id, "last_welcome_msg", msg_id)


def get_welcome_timer(chat_id: int) -> int:
    """Seconds after which the welcome message auto-deletes. 0 = off."""
    return get_int(chat_id, "welcome_timer", 0)


def set_welcome_timer(chat_id: int, seconds: int) -> None:
    set_setting(chat_id, "welcome_timer", seconds)


def get_goodbye_timer(chat_id: int) -> int:
    """Seconds after which the goodbye message auto-deletes. 0 = off."""
    return get_int(chat_id, "goodbye_timer", 0)


def set_goodbye_timer(chat_id: int, seconds: int) -> None:
    set_setting(chat_id, "goodbye_timer", seconds)


def get_botclean_timer(chat_id: int) -> int:
    """Seconds after which the bot's own reply messages auto-delete. 0 = off."""
    return get_int(chat_id, "botclean_timer", 0)


def set_botclean_timer(chat_id: int, seconds: int) -> None:
    set_setting(chat_id, "botclean_timer", seconds)


# ---------------------------------------------------------------------- rules
def get_rules(chat_id: int) -> str:
    return get_setting(chat_id, "rules", "")


def set_rules(chat_id: int, text: str) -> None:
    set_setting(chat_id, "rules", text)


def clear_rules(chat_id: int) -> None:
    set_setting(chat_id, "rules", "")


# ---------------------------------------------------------------------- locks
def set_lock(chat_id: int, lock_type: str, locked: bool) -> None:
    with _LOCK, _connect() as conn:
        if locked:
            conn.execute(
                "INSERT OR IGNORE INTO locks (chat_id, lock_type) VALUES (?,?)",
                (chat_id, lock_type),
            )
        else:
            conn.execute(
                "DELETE FROM locks WHERE chat_id=? AND lock_type=?", (chat_id, lock_type)
            )


def is_locked(chat_id: int, lock_type: str) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM locks WHERE chat_id=? AND lock_type=?", (chat_id, lock_type)
        ).fetchone()
        return row is not None


def list_locks(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT lock_type FROM locks WHERE chat_id=? ORDER BY lock_type", (chat_id,)
        ).fetchall()
        return [r["lock_type"] for r in rows]


# -------------------------------------------------------------------- antiflood
def get_flood_limit(chat_id: int) -> int:
    return get_int(chat_id, "flood_limit", 0)  # 0 = disabled


def set_flood_limit(chat_id: int, n: int) -> None:
    set_setting(chat_id, "flood_limit", n)


def get_flood_mode(chat_id: int) -> str:
    return get_setting(chat_id, "flood_mode", "mute")


def set_flood_mode(chat_id: int, mode: str) -> None:
    set_setting(chat_id, "flood_mode", mode)


# ------------------------------------------------------------------ blacklist
def add_blacklist(chat_id: int, word: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blacklist (chat_id, word) VALUES (?,?)",
            (chat_id, word.lower()),
        )


def remove_blacklist(chat_id: int, word: str) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM blacklist WHERE chat_id=? AND word=?", (chat_id, word.lower())
        )
        return cur.rowcount > 0


def list_blacklist(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT word FROM blacklist WHERE chat_id=? ORDER BY word", (chat_id,)
        ).fetchall()
        return [r["word"] for r in rows]


def clear_blacklist(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM blacklist WHERE chat_id=?", (chat_id,))


def get_blacklist_mode(chat_id: int) -> str:
    return get_setting(chat_id, "blacklist_mode", "del")


def set_blacklist_mode(chat_id: int, mode: str) -> None:
    set_setting(chat_id, "blacklist_mode", mode)


def add_blsticker(chat_id: int, file_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blstickers (chat_id, file_id) VALUES (?,?)",
            (chat_id, file_id),
        )


def remove_blsticker(chat_id: int, file_id: str) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM blstickers WHERE chat_id=? AND file_id=?", (chat_id, file_id)
        )
        return cur.rowcount > 0


def list_blstickers(chat_id: int):
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT file_id FROM blstickers WHERE chat_id=?", (chat_id,)
        ).fetchall()
        return [r["file_id"] for r in rows]


def is_blsticker(chat_id: int, file_id: str) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM blstickers WHERE chat_id=? AND file_id=?", (chat_id, file_id)
        ).fetchone()
        return row is not None


# -------------------------------------------------------------------- reports
def get_reports(chat_id: int) -> bool:
    return get_bool(chat_id, "reports", True)


def set_reports(chat_id: int, on: bool) -> None:
    set_bool(chat_id, "reports", on)


# ------------------------------------------------------------------------ afk
def set_afk(user_id: int, reason: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO afk (user_id, reason) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason",
            (user_id, reason),
        )


def get_afk(user_id: int):
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT reason FROM afk WHERE user_id=?", (user_id,)).fetchone()
        return row["reason"] if row else None


def clear_afk(user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM afk WHERE user_id=?", (user_id,))


# --------------------------------------------------------------------- captcha
def add_pending_captcha(chat_id: int, user_id: int, ttl: int = 300) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO pending_captcha (chat_id, user_id, expires) VALUES (?,?,?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET expires=excluded.expires",
            (chat_id, user_id, int(time.time()) + ttl),
        )


def has_pending_captcha(chat_id: int, user_id: int) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT expires FROM pending_captcha WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        return bool(row and row["expires"] > time.time())


def remove_pending_captcha(chat_id: int, user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "DELETE FROM pending_captcha WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )


# ---------------------------------------------------------- connections
def set_connection(user_id: int, chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO connections (user_id, chat_id) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id",
            (user_id, chat_id),
        )


def get_connection(user_id: int):
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT chat_id FROM connections WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["chat_id"] if row else None


def del_connection(user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM connections WHERE user_id=?", (user_id,))


def remember_chat(chat_id: int, title: str, type_: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO known_chats (chat_id, title, type) VALUES (?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, type=excluded.type",
            (chat_id, title or "", type_ or ""),
        )


def list_known_chats():
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT chat_id, title, type FROM known_chats ORDER BY title"
        ).fetchall()


# ------------------------------------------------------------- member tracker
# Used by /zombies and /tagall.
def record_member(chat_id: int, user_id: int, name: str = "") -> None:
    now = int(time.time())
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO members (chat_id, user_id, name, last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen",
            (chat_id, user_id, name or "", now),
        )


def list_members(chat_id: int):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT user_id, name, last_seen FROM members WHERE chat_id=? ORDER BY last_seen DESC",
            (chat_id,),
        ).fetchall()


def recent_members(chat_id: int, limit: int = 50):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT user_id, name FROM members WHERE chat_id=? ORDER BY last_seen DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()


def forget_member(chat_id: int, user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM members WHERE chat_id=? AND user_id=?", (chat_id, user_id))


# ------------------------------------------------------------------ anti-raid
def get_raid(chat_id: int):
    """Return (joins, seconds); (0, 0) means disabled."""
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT joins, seconds FROM raid_settings WHERE chat_id=?", (chat_id,)
        ).fetchone()
        return (row["joins"], row["seconds"]) if row else (0, 0)


def set_raid(chat_id: int, joins: int, seconds: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO raid_settings (chat_id, joins, seconds) VALUES (?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET joins=excluded.joins, seconds=excluded.seconds",
            (chat_id, joins, seconds),
        )


def disable_raid(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM raid_settings WHERE chat_id=?", (chat_id,))


# --------------------------------------------------------------- welcome media
def get_welcome_media(chat_id: int) -> str:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT file_id FROM welcome_media WHERE chat_id=?", (chat_id,)
        ).fetchone()
        return row["file_id"] if row else ""


def set_welcome_media(chat_id: int, file_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO welcome_media (chat_id, file_id) VALUES (?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET file_id=excluded.file_id",
            (chat_id, file_id),
        )


def clear_welcome_media(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM welcome_media WHERE chat_id=?", (chat_id,))


# ------------------------------------------------------------------ scheduler
def add_schedule(chat_id: int, time_hhmm: str, text: str) -> int:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO schedules (chat_id, time_hhmm, text) VALUES (?,?,?)",
            (chat_id, time_hhmm, text),
        )
        return cur.lastrowid


def list_schedules(chat_id: int):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT id, time_hhmm, text FROM schedules WHERE chat_id=? ORDER BY time_hhmm",
            (chat_id,),
        ).fetchall()


def get_schedule(sched_id: int):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT id, chat_id, time_hhmm, text FROM schedules WHERE id=?", (sched_id,)
        ).fetchone()


def delete_schedule(sched_id: int) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute("DELETE FROM schedules WHERE id=?", (sched_id,))
        return cur.rowcount > 0


def list_all_schedules():
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT id, chat_id, time_hhmm, text FROM schedules ORDER BY chat_id, time_hhmm"
        ).fetchall()


# ------------------------------------------------------------------ slowmode
def get_slowmode(chat_id: int) -> int:
    """Seconds between messages. 0 = off."""
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT seconds FROM slowmode WHERE chat_id=?", (chat_id,)).fetchone()
        return row["seconds"] if row else 0


def set_slowmode(chat_id: int, seconds: int) -> None:
    with _LOCK, _connect() as conn:
        if seconds <= 0:
            conn.execute("DELETE FROM slowmode WHERE chat_id=?", (chat_id,))
        else:
            conn.execute(
                "INSERT INTO slowmode (chat_id, seconds) VALUES (?,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET seconds=excluded.seconds",
                (chat_id, seconds),
            )


# --------------------------------------------------------------- federations
def create_fed(fed_id: str, name: str, owner_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO feds (fed_id, name, owner_id) VALUES (?,?,?)", (fed_id, name, owner_id)
        )
        conn.execute(
            "INSERT OR IGNORE INTO fed_admins (fed_id, user_id) VALUES (?,?)",
            (fed_id, owner_id),
        )


def get_fed(fed_id: str):
    with _LOCK, _connect() as conn:
        return conn.execute("SELECT fed_id, name, owner_id FROM feds WHERE fed_id=?", (fed_id,)).fetchone()


def delete_fed(fed_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM feds WHERE fed_id=?", (fed_id,))
        conn.execute("DELETE FROM fed_chats WHERE fed_id=?", (fed_id,))
        conn.execute("DELETE FROM fed_admins WHERE fed_id=?", (fed_id,))
        conn.execute("DELETE FROM fed_bans WHERE fed_id=?", (fed_id,))
        conn.execute("DELETE FROM chat_fed WHERE fed_id=?", (fed_id,))


def my_feds(owner_id: int):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT fed_id, name FROM feds WHERE owner_id=? ORDER BY name", (owner_id,)
        ).fetchall()


def link_chat_fed(chat_id: int, fed_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO chat_fed (chat_id, fed_id) VALUES (?,?)", (chat_id, fed_id))
        conn.execute(
            "INSERT OR IGNORE INTO fed_chats (fed_id, chat_id) VALUES (?,?)", (fed_id, chat_id)
        )


def unlink_chat_fed(chat_id: int) -> None:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT fed_id FROM chat_fed WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            conn.execute("DELETE FROM fed_chats WHERE fed_id=? AND chat_id=?", (row["fed_id"], chat_id))
        conn.execute("DELETE FROM chat_fed WHERE chat_id=?", (chat_id,))


def get_chat_fed(chat_id: int):
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT fed_id FROM chat_fed WHERE chat_id=?", (chat_id,)).fetchone()
        return row["fed_id"] if row else None


def fed_chats(fed_id: str):
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT chat_id FROM fed_chats WHERE fed_id=?", (fed_id,)).fetchall()
        return [r["chat_id"] for r in rows]


def is_fed_admin(fed_id: str, user_id: int) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM fed_admins WHERE fed_id=? AND user_id=?", (fed_id, user_id)
        ).fetchone()
        return row is not None


def fed_promote(fed_id: str, user_id: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO fed_admins (fed_id, user_id) VALUES (?,?)", (fed_id, user_id)
        )


def fed_demote(fed_id: str, user_id: int) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM fed_admins WHERE fed_id=? AND user_id=?", (fed_id, user_id)
        )
        return cur.rowcount > 0


def fed_admins(fed_id: str):
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT user_id FROM fed_admins WHERE fed_id=?", (fed_id,)).fetchall()
        return [r["user_id"] for r in rows]


def fban_user(fed_id: str, user_id: int, reason: str, banned_by: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO fed_bans (fed_id, user_id, reason, banned_by) VALUES (?,?,?,?) "
            "ON CONFLICT(fed_id, user_id) DO UPDATE SET reason=excluded.reason, banned_by=excluded.banned_by",
            (fed_id, user_id, reason or "", banned_by),
        )


def unfban_user(fed_id: str, user_id: int) -> bool:
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM fed_bans WHERE fed_id=? AND user_id=?", (fed_id, user_id)
        )
        return cur.rowcount > 0


def is_fed_banned(fed_id: str, user_id: int) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM fed_bans WHERE fed_id=? AND user_id=?", (fed_id, user_id)
        ).fetchone()
        return row is not None


def fed_ban_reason(fed_id: str, user_id: int) -> str:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT reason FROM fed_bans WHERE fed_id=? AND user_id=?", (fed_id, user_id)
        ).fetchone()
        return row["reason"] if row else ""


def fed_banlist(fed_id: str):
    with _LOCK, _connect() as conn:
        return conn.execute(
            "SELECT user_id, reason FROM fed_bans WHERE fed_id=? ORDER BY user_id", (fed_id,)
        ).fetchall()
