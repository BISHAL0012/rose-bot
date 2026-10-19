"""Rose-style Telegram group management bot — entry point.

Setup:
  1. cp .env.example .env   (then put your BotFather token in .env)
  2. pip install -r requirements.txt
  3. python bot.py
"""

import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # <-- MUST be called so BOT_TOKEN is read from .env

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application

import database
from handlers import register_all

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("rose_bot")


async def post_init(app):
    """Runs once after the Application is built: re-arm saved schedules."""
    try:
        from handlers import scheduler
        n = scheduler.reschedule_all(app)
        if n:
            logger.info("Re-armed %d scheduled announcement(s).", n)
    except Exception as e:
        logger.warning("Could not re-arm schedules: %s", e)


def main():
    database.init_db()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "your_token_here":
        sys.exit("❌ BOT_TOKEN পাওয়া যায়নি! .env ফাইলে BOT_TOKEN=... বসান।")

    app = Application.builder().token(token).post_init(post_init).build()
    register_all(app)

    logger.info("Bot is starting…")
    while True:
        try:
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except NetworkError as e:
            logger.warning("Network problem (%s) — 10 সেকেন্ড পর আবার চেষ্টা…", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
