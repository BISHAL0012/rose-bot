# 🌹 Rose-Style Telegram Group Management Bot

Rose বটের মতো ফিচারসম্পন্ন টেলিগ্রাম গ্রুপ ম্যানেজমেন্ট বট — Python দিয়ে তৈরি।

---

## 🚀 সেটআপ (Setup)

### ১. টোকেন নিন (@BotFather থেকে)
1. টেলিগ্রামে **@BotFather** কে মেসেজ দিন
2. `/newbot` পাঠান → বটের নাম ও username দিন
3. BotFather যে **token** দেবে সেটা কপি করুন

### ২. প্রজেক্ট চালু করুন
```bash
cd rose_bot
cp .env.example .env
# .env ফাইলে BOT_TOKEN=... এর জায়গায় আপনার টোকেন বসান
pip install -r requirements.txt
python bot.py
```

### ৩. গ্রুপে যোগ করুন
1. বটকে আপনার গ্রুপে অ্যাড করুন
2. বটকে **Admin** করুন এবং এই পারমিশনগুলো দিন:
   - Delete messages, Ban users, Pin messages, Invite users (promote-এর জন্য)
3. `/help` লিখে সব কমান্ড দেখুন

> ⚠️ সব সেটিংস `data.db` (SQLite) ফাইলে সেভ থাকে — বট রিস্টার্ট হলেও মুছবে না।

---

## 📖 কমান্ড লিস্ট (Full Command List)

### 👮 Admin
| কমান্ড | কাজ |
|---|---|
| `/ban` | ব্যান (রিপ্লাই / ID / @username) |
| `/tban <ID> 5m` | সাময়িক ব্যান (5m/2h/1d/1w) |
| `/unban <ID/@username>` | আনব্যান |
| `/kick` | কিক |
| `/mute` | মিউট |
| `/tmute <ID> 5m` | সাময়িক মিউট |
| `/unmute` | আনমিউট |
| `/promote` | অ্যাডমিন বানানো |
| `/demote` | অ্যাডমিন থেকে নামানো |
| `/pin` `/unpin` `/unpinall` | মেসেজ পিন |
| `/announce <মেসেজ>` | 📢 ঘোষণা পাঠানো |
| `/announce pin <মেসেজ>` | 📢 ঘোষণা + পিন |
| `/purge` | রিপ্লাই করা মেসেজ থেকে সব ডিলিট |
| `/del` | রিপ্লাই করা মেসেজ ডিলিট |

### ⚠️ Warns
`/warn` `/unwarn` `/warns` `/resetwarns` `/warnlimit <n>` `/warnmode <ban|mute|kick>` `/addwarn <শব্দ>` `/nowarn <শব্দ>` `/warnfilters`

### 🔎 Filters & 📝 Notes
`/filter <শব্দ> <উত্তর>` `/filters` `/stop <শব্দ>` `/stopall`
`/save <নাম> <টেক্সট>` `/get <নাম>` `/#নাম` `/notes` `/clear <নাম>` `/clearall` `/privatenotes <on|off>`
- `{first}` `{last}` `{username}` `{chatname}` প্লেসহোল্ডার সাপোর্ট করে
- `[লেখা](https://url)` দিলে ইনলাইন বাটন তৈরি হয়

### 👋 Welcome / Goodbye / 📜 Rules
`/setwelcome` `/resetwelcome` `/welcome <on|off>`
`/setgoodbye` `/resetgoodbye` `/goodbye <on|off>`
`/welcomemute <on|off>` — নতুন মেম্বারকে "✅ আমি মানুষ" বাটনে ট্যাপ করতে হবে (৫ মিনিটে না করলে কিক)
`/cleanwelcome <on|off>` — পুরনো welcome মেসেজ অটো ডিলিট
`/welcometimer <সেকেন্ড|off>` — welcome মেসেজ নির্দিষ্ট সময় পর অটো ডিলিট (যেমন `/welcometimer 30`)
`/goodbyetimer <সেকেন্ড|off>` — goodbye মেসেজ নির্দিষ্ট সময় পর অটো ডিলিট (যেমন `/goodbyetimer 30`)
`/botclean <সেকেন্ড|off>` — বটের নিজের reply মেসেজ নির্দিষ্ট সময় পর অটো ডিলিট (যেমন `/botclean 30`)
`/setrules` `/rules` `/clearrules`
`/setwelcomemedia` (ছবিতে রিপ্লাই করে) — welcome মেসেজ ছবিসহ যাবে `/clearwelcomemedia`

### 🔐 Locks — `/lock <type>` `/unlock <type>` `/locks` `/locktypes`
sticker, gif, media, photo, video, document, audio, voice, videonote, url, bots, forward, contact, location, poll, game, rtl, button, inline, command, all

### 🌊 Anti-flood
`/setflood <n>` (0 = বন্ধ) `/flood` `/setfloodmode <ban|kick|mute|warn>`

### 🚫 Blacklist
`/addblacklist <শব্দ>` `/unblacklist` `/blacklist` `/blacklistmode <off|del|warn|ban|mute|kick>` `/blsticker` `/unblsticker` `/blstickers`

### 🚨 Reports
`/report` (অপরাধমূলক মেসেজে রিপ্লাই করে) — অ্যাডমিনদের কাছে Ban/Kick/Mute/Del বাটনসহ যাবে
`/reports <on|off>`

### 🧟 Zombies
`/zombies` — deleted account খুঁজে বের করো `/zombies clean` — সবাইকে ব্যান করো

### 📢 Tagall
`/tagall <মেসেজ>` — সাম্প্রতিক ~৫০ জন active মেম্বারকে ট্যাগ করো

### 🛡️ Anti-raid
`/raid <joins> <seconds>` (যেমন `/raid 8 30`) `/raid off` `/raidstatus`
নির্দিষ্ট সময়ে অনেক join হলে ১০ মিনিটের raid mode — নতুন join-রা auto-mute

### 💾 Backup
`/export` — সব সেটিংস JSON ফাইলে `/import` (ফাইলে রিপ্লাই করে) — রিস্টোর

### ⏰ Scheduled announcements
`/schedule <HH:MM> <মেসেজ>` — প্রতিদিন ঢাকা টাইমে auto message (বাটন: `[লেখা](url|red)`)
`/schedules` `/unschedule <id>`

### 🐢 Slowmode
`/slowmode <seconds|off>` (৫–৩০০) — bot-enforced, অ্যাডমিনরা exempt

### 🌐 Federations
`/newfed <নাম>` `/delfed` `/fedinfo`
`/joinfed <fed_id>` `/leavefed`
`/fban <user> [কারণ]` `/unfban <user>` `/fedbanlist` — সব fed গ্রুপে একসাথে ব্যান
`/fedpromote <user>` `/feddemote <user>` — fed admin (শুধু owner)
Fed-banned ইউজার join করলেই auto-ban

### ℹ️ বিবিধ
`/start` `/help` (বাটন মেনু) `/info` `/id` `/admins` `/afk <কারণ>` `/ping`

### 🔗 Connect (PM থেকে গ্রুপ চালানো)
`/connect` — গ্রুপে দিলে ওই গ্রুপে কানেক্ট হবে; PM-এ দিলে গ্রুপ বেছে নেওয়ার বাটন আসবে
`/disconnect` — সংযোগ বিচ্ছিন্ন
কানেক্ট থাকলে PM-এ পাঠানো কমান্ড (যেমন `/announce`, `/setwelcome`) ওই গ্রুপে কাজ করবে।

---

## 🛠️ ফাইল গঠন
```
rose_bot/
  bot.py              # এন্ট্রি পয়েন্ট (load_dotenv + polling)
  database.py         # SQLite persistence (data.db)
  utils.py            # হেলপার (time parse, admin check, user resolve)
  handlers/
    admin.py          # ban/kick/mute/promote/pin/purge/del/announce
    connection.py     # /connect /disconnect (PM থেকে গ্রুপ চালানো)
    warns.py          # warn সিস্টেম
    filters_notes.py  # ফিল্টার ও নোট
    welcome.py        # welcome/goodbye/captcha/rules (+ photo welcome)
    locks.py          # লক সিস্টেম
    antiflood.py      # অ্যান্টি-ফ্লাড
    antiraid.py       # raid protection
    blacklist.py      # ব্ল্যাকলিস্ট
    reports.py        # রিপোর্ট সিস্টেম
    zombies.py        # deleted account scan + member tracker
    tagall.py         # /tagall
    backup.py         # /export /import
    scheduler.py      # daily scheduled announcements
    slowmode.py       # bot-enforced slowmode
    federation.py     # federations + fed-ban
    misc.py           # start/help/info/afk/ping
  requirements.txt
  .env.example
  README.md
```

## 📄 License
Personal use. Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot).

## FadeHost deploy
1. Push this folder to a GitHub repo (do NOT upload `.env`).
2. FadeHost panel → Apps → Host → Telegram bot → your repository.
3. Environment table: `BOT_TOKEN=<token from BotFather>` (one KEY=value per line).
4. Region: Asia Pacific (Singapore). Deploy → send /start to the bot.
The SQLite DB lives in /data on FadeHost (survives deploys); locally it stays next to the code.
