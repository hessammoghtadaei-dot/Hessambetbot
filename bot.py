
import os
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters


TOKEN = os.environ["BOT_TOKEN"]

# ساعت ایران
IRAN_TZ = ZoneInfo("Asia/Tehran")

# فایل ذخیره بازی‌ها
DATA_FILE = "matches.json"


# -----------------------------
# Team logos
# -----------------------------

TEAM_LOGOS = {
    "real madrid": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/spain/Real%20Madrid.svg",
    "barcelona": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/spain/Barcelona.svg",
    "atletico madrid": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/spain/Atletico%20Madrid.svg",

    "liverpool": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/england/Liverpool.svg",
    "arsenal": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/england/Arsenal.svg",
    "chelsea": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/england/Chelsea.svg",
    "manchester united": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/england/Manchester%20United.svg",
    "manchester city": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/england/Manchester%20City.svg",

    "bayern munich": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/germany/Bayern%20Munich.svg",
    "borussia dortmund": "https://raw.githubusercontent.com/JoseArroyave/football-logos/main/logos/germany/Borussia%20Dortmund.svg",
}


# -----------------------------
# Database
# -----------------------------

def load_matches():
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_matches(matches):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)


# -----------------------------
# Parse matches
# -----------------------------

def parse_matches(text):
    """
    Expected format:

    Real Madrid - Barcelona | 31/08/2026 | 23:00
    Liverpool - Arsenal | 01/09/2026 | 22:30
    """

    matches = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]

        if len(parts) != 3:
            continue

        teams, date_text, time_text = parts

        if " - " not in teams:
            continue

        home, away = [x.strip() for x in teams.split(" - ", 1)]

        try:
            dt = datetime.strptime(
                f"{date_text} {time_text}",
                "%d/%m/%Y %H:%M"
            ).replace(tzinfo=IRAN_TZ)

        except ValueError:
            continue

        matches.append({
            "home": home,
            "away": away,
            "datetime": dt.isoformat(),
            "sent_24h": False,
            "sent_today": False
        })

    return matches


# -----------------------------
# Commands
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "⚽️ Hessambetbot\n\n"
        "برای اضافه کردن بازی‌ها، هر بازی را در یک خط بفرست:\n\n"
        "Real Madrid - Barcelona | 31/08/2026 | 23:00\n"
        "Liverpool - Arsenal | 01/09/2026 | 22:30\n\n"
        "همه ساعت‌ها به وقت ایران هستند."
    )

    await update.message.reply_text(text)


async def add_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    new_matches = parse_matches(text)

    if not new_matches:
        await update.message.reply_text(
            "❌ قالب بازی‌ها درست نیست.\n\n"
            "نمونه:\n"
            "Real Madrid - Barcelona | 31/08/2026 | 23:00"
        )
        return

    matches = load_matches()

    added = 0

    for new_match in new_matches:

        duplicate = False

        for old_match in matches:

            if (
                old_match["home"].lower() == new_match["home"].lower()
                and old_match["away"].lower() == new_match["away"].lower()
                and old_match["datetime"] == new_match["datetime"]
            ):
                duplicate = True
                break

        if not duplicate:
            matches.append(new_match)
            added += 1

    save_matches(matches)

    await update.message.reply_text(
        f"✅ {added} بازی اضافه شد.\n\n"
        f"تعداد کل بازی‌های ذخیره‌شده: {len(matches)}"
    )


# -----------------------------
# Daily notification
# -----------------------------

async def check_matches(application):

    now = datetime.now(IRAN_TZ)

    matches = load_matches()

    changed = False

    # این مقدار را بعداً از Chat ID گروه می‌گیریم
    chat_id = os.environ.get("GROUP_CHAT_ID")

    if not chat_id:
        return

    for match in matches:

        match_time = datetime.fromisoformat(match["datetime"])

        hours_left = (match_time - now).total_seconds() / 3600

        # -------------------------
        # 24 hours before
        # -------------------------

        if (
            23 <= hours_left <= 25
            and not match["sent_24h"]
        ):

            await send_match_message(
                application,
                chat_id,
                match,
                "⏳ 24 HOURS TO GO"
            )

            match["sent_24h"] = True
            changed = True

        # -------------------------
        # Match day
        # -------------------------

        if (
            match_time.date() == now.date()
            and match_time > now
            and not match["sent_today"]
        ):

            await send_match_message(
                application,
                chat_id,
                match,
                "🔥 TODAY'S MATCH"
            )

            match["sent_today"] = True
            changed = True

    if changed:
        save_matches(matches)


# -----------------------------
# Send match
# -----------------------------

async def send_match_message(application, chat_id, match, title):

    home = match["home"]
    away = match["away"]

    dt = datetime.fromisoformat(match["datetime"])

    date_text = dt.strftime("%d/%m/%Y")
    time_text = dt.strftime("%H:%M")

    home_logo = TEAM_LOGOS.get(home.lower())
    away_logo = TEAM_LOGOS.get(away.lower())

    caption = (
        f"{title}\n\n"
        f"⚽️ {home}\n"
        f"🆚\n"
        f"⚽️ {away}\n\n"
        f"📅 {date_text}\n"
        f"🕐 {time_text}\n\n"
        f"🇮🇷 Iran Time"
    )

    # اگر لوگوی تیم اول موجود باشد
    if home_logo:

        await application.bot.send_photo(
            chat_id=chat_id,
            photo=home_logo,
            caption=caption
        )

    else:

        await application.bot.send_message(
            chat_id=chat_id,
            text=caption
        )


# -----------------------------
# Main
# -----------------------------

async def main():

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            add_matches
        )
    )

    await application.initialize()
    await application.start()

    await check_matches(application)

    await application.stop()
    await application.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
