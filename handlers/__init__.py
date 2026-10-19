"""Register every handler module with the application.

Watcher groups (lower runs first):
  1 = locks, 2 = antiflood, 3 = warn auto-filter, 4 = filters,
  5 = hashtag notes, 6 = blacklist, 7 = afk
"""

from . import (
    admin,
    antiflood,
    antiraid,
    backup,
    blacklist,
    connection,
    federation,
    filters_notes,
    locks,
    misc,
    reports,
    scheduler,
    slowmode,
    tagall,
    warns,
    welcome,
    zombies,
)


def register_all(app):
    for module in (connection, admin, warns, filters_notes, welcome, locks,
                   antiflood, antiraid, blacklist, reports, misc, zombies,
                   tagall, backup, scheduler, slowmode, federation):
        module.register(app)
