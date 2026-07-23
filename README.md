# RemindMeBot

A simple, honest personal reminder bot for Telegram. Users type `/remind`
with a time and a message, and the bot messages them back at the right
moment. Nothing more, nothing less — which is exactly what makes it easy to
get approved for Telegram Ads.

## Features
- `/remind in 30m Call John`
- `/remind in 2h Submit report`
- `/remind at 17:00 Pick up kids`
- `/remind at 2026-07-25 09:00 Dentist appointment`
- `/list` — see upcoming reminders
- `/cancel <id>` — cancel one
- `/privacy` — shows the bot's privacy policy (see below)

Reminders are stored in SQLite, and jobs are automatically re-scheduled if
the bot restarts, so nothing is lost.

---

## 1. Create the bot on Telegram

1. Open Telegram, search for **@BotFather**.
2. Send `/newbot`, choose a name and a username ending in `bot`
   (e.g. `RemindMe247Bot`).
3. Copy the token BotFather gives you — you'll need it as `BOT_TOKEN`.
4. Optional but recommended for Ads review — send BotFather:
   - `/setdescription` → a one-line honest description, e.g.
     *"Set personal reminders and never forget a task again."*
   - `/setabouttext` → same idea, short and clear.
   - `/setuserpic` → upload a simple, clean icon (no copyrighted logos).

## 2. Push this code to GitHub

git init
git add .
git commit -m "Initial commit: RemindMeBot"
git branch -M main
git remote add origin https://github.com/<your-username>/remindme-bot.git
git push -u origin main

## 3. Deploy on Railway

1. Go to railway.app and log in with GitHub.
2. New Project → Deploy from GitHub repo → select remindme-bot.
3. Railway detects Python automatically via railway.json / Nixpacks.
4. Add variables: BOT_TOKEN, TIMEZONE, DB_PATH=/data/reminders.db
5. Add a Volume mounted at /data so reminders survive redeploys.
6. Deploy and check Logs for "RemindMeBot starting (polling mode)..."

(full details in the actual file)
