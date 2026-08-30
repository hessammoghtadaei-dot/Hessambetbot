import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = os.environ["GROUP_CHAT_ID"]

IRAN_TZ = ZoneInfo("Asia/Tehran")
DATA_FILE = "matches.json"


def load_matches():
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_matches(matches):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)


def parse_matches(text):
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

        home, away = teams.split(" - ", 1)

        try:
            dt = datetime.strptime(
                f"{date_text} {time_text}",
                "%d/%m/%Y %H:%M"
            ).replace(tzinfo=IRAN_TZ)
        except ValueError:
            continue

        matches.append({
            "home": home.strip(),
            "away": away.strip(),
            "datetime": dt.isoformat(),
            "sent_24h": False,
            "sent_today": False,
        })

    return matches


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "⚽️ Hessambetbot فعال است.\n\n"
        "برای اضافه کردن بازی‌ها، هر بازی را در یک خط بفرست:\n\n"
        "Real Madrid - Barcelona | 31/08/2026 | 23:00\n"
        "Liverpool - Arsenal | 01/09/2026 | 22:30\n\n"
        "ساعت‌ها به وقت ایران هستند."
    )


async def receive_matches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # فقط پیام خصوصی از طرف صاحب ربات را قبول می‌کنیم
    if update.effective_chat.type != "private":
        return

    matches = parse_matches(update.message.text)

    if not matches:
        await update.message.reply_text(
            "❌ قالب درست نیست.\n\n"
            "نمونه:\n"
            "Real Madrid - Barcelona | 31/08/2026 | 23:00"
        )
        return

    old_matches = load_matches()

    added = 0

    for new_match in matches:

        exists = any(
            old["home"].lower() == new_match["home"].lower()
            and old["away"].lower() == new_match["away"].lower()
            and old["datetime"] == new_match["datetime"]
            for old in old_matches
        )

        if not exists:
            old_matches.append(new_match)
            added += 1

    save_matches(old_matches)

    await update.message.reply_text(
        f"✅ {added} بازی اضافه شد.\n"
        f"📋 مجموع بازی‌ها: {len(old_matches)}"
    )


async def check_matches(application):

    now = datetime.now(IRAN_TZ)

    matches = load_matches()

    changed = False

    for match in matches:

        match_time = datetime.fromisoformat(match["datetime"])

        hours_left = (
            match_time - now
        ).total_seconds() / 3600

        # 24 ساعت قبل
        if 23 <= hours_left <= 25 and not match["sent_24h"]:

            await send_match(
                application,
                match,
                "⏳ 24 HOURS TO GO"
            )

            match["sent_24h"] = True
            changed = True

        # روز مسابقه
        elif (
            match_time.date() == now.date()
            and match_time > now
            and not match["sent_today"]
        ):

            await send_match(
                application,
                match,
                "🔥 TODAY'S MATCH"
            )

            match["sent_today"] = True
            changed = True

    if changed:
        save_matches(matches)


async def send_match(application, match, title):

    dt = datetime.fromisoformat(match["datetime"])

    text = (
        f"{title}\n\n"
        f"⚽️ {match['home']}\n"
        f"🆚\n"
        f"⚽️ {match['away']}\n\n"
        f"📅 {dt.strftime('%d/%m/%Y')}\n"
        f"🕐 {dt.strftime('%H:%M')}\n"
        f"🇮🇷 Iran Time"
    )

    await application.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text
    )


async def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_matches
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
