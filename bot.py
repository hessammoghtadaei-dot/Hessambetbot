import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])

# Telegram user ID of Hessam
OWNER_ID = 174537663

TEHRAN = ZoneInfo("Asia/Tehran")

MATCHES_FILE = "matches.json"
STATE_FILE = "state.json"


# =========================
# TELEGRAM API
# =========================

def telegram(method, data=None):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if data:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded)
    else:
        request = urllib.request.Request(url)

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):

    telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text
        }
    )


# =========================
# FILE STORAGE
# =========================

def load_json(filename, default):

    try:

        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception:

        return default


def save_json(filename, data):

    with open(filename, "w", encoding="utf-8") as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================
# PARSE MATCHES
# =========================

def parse_matches(text):

    result = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        parts = [
            item.strip()
            for item in line.split("|")
        ]

        if len(parts) != 3:
            continue

        teams, date_text, time_text = parts

        if " - " not in teams:
            continue

        home, away = teams.split(" - ", 1)

        try:

            match_time = datetime.strptime(
                f"{date_text} {time_text}",
                "%d/%m/%Y %H:%M"
            ).replace(
                tzinfo=TEHRAN
            )

        except ValueError:

            continue

        result.append(
            {
                "home": home.strip(),
                "away": away.strip(),
                "datetime": match_time.isoformat(),
                "sent_24h": False,
                "sent_today": False
            }
        )

    return result


# =========================
# ADD MATCHES
# =========================

def add_matches(new_matches):

    matches = load_json(
        MATCHES_FILE,
        []
    )

    added = 0

    for new_match in new_matches:

        duplicate = any(

            item["home"].lower()
            == new_match["home"].lower()

            and

            item["away"].lower()
            == new_match["away"].lower()

            and

            item["datetime"]
            == new_match["datetime"]

            for item in matches
        )

        if not duplicate:

            matches.append(new_match)

            added += 1

    save_json(
        MATCHES_FILE,
        matches
    )

    return added, len(matches)


# =========================
# GET TELEGRAM UPDATES
# =========================

def get_updates(offset):

    data = {
        "timeout": 1
    }

    if offset:

        data["offset"] = offset

    response = telegram(
        "getUpdates",
        data
    )

    return response.get(
        "result",
        []
    )


# =========================
# PROCESS TELEGRAM MESSAGES
# =========================

def process_updates():

    state = load_json(
        STATE_FILE,
        {
            "offset": 0
        }
    )

    offset = state.get(
        "offset",
        0
    )

    updates = get_updates(
        offset
    )

    for update in updates:

        state["offset"] = (
            update["update_id"] + 1
        )

        message = update.get(
            "message"
        )

        if not message:
            continue

        chat = message.get(
            "chat",
            {}
        )

        # Only private messages
        if chat.get("type") != "private":
            continue

        user = message.get(
            "from",
            {}
        )

        # Only Hessam can add matches
        if user.get("id") != OWNER_ID:
            continue

        text = message.get(
            "text",
            ""
        ).strip()

        # /start
        if text == "/start":

            send_message(

                chat["id"],

                "⚽️ Hessambetbot فعال است.\n\n"
                "فرمت ارسال بازی:\n\n"
                "Real Madrid - Barcelona | 31/08/2026 | 23:00\n"
                "Liverpool - Arsenal | 01/09/2026 | 22:30\n\n"
                "هر بازی در یک خط."
            )

            continue

        # Parse matches
        new_matches = parse_matches(
            text
        )

        if not new_matches:

            send_message(

                chat["id"],

                "❌ فرمت بازی قابل تشخیص نیست.\n\n"
                "نمونه صحیح:\n"
                "Real Madrid - Barcelona | 31/08/2026 | 23:00"
            )

            continue

        # Save matches
        added, total = add_matches(
            new_matches
        )

        send_message(

            chat["id"],

            f"✅ {added} بازی اضافه شد.\n"
            f"📋 مجموع بازی‌ها: {total}"
        )

    save_json(
        STATE_FILE,
        state
    )


# =========================
# 24 HOURS BEFORE MATCH
# =========================

def check_24_hour_notifications(
    now,
    matches
):

    changed = False

    for match in matches:

        # Already sent
        if match.get(
            "sent_24h",
            False
        ):
            continue

        match_time = datetime.fromisoformat(
            match["datetime"]
        )

        notification_time = (
            match_time
            - timedelta(hours=24)
        )

        # Important:
        # If GitHub Actions was delayed,
        # the notification is still sent.
        if (
            now >= notification_time
            and now < match_time
        ):

            text = (

                "⏳ ۲۴ ساعت تا شروع مسابقه\n\n"

                f"⚽️ {match['home']}\n"
                "🆚\n"
                f"⚽️ {match['away']}\n\n"

                f"📅 {match_time.strftime('%d/%m/%Y')}\n"
                f"🕐 {match_time.strftime('%H:%M')}\n"

                "🇮🇷 به وقت ایران"
            )

            send_message(
                GROUP_CHAT_ID,
                text
            )

            match["sent_24h"] = True

            changed = True

    return changed


# =========================
# MATCH DAY - 12:00
# =========================

def check_today_notifications(
    now,
    matches
):

    changed = False

    # Only around 12:00 Tehran time
    if now.hour != 12:
        return False

    if now.minute > 4:
        return False

    for match in matches:

        # Already sent
        if match.get(
            "sent_today",
            False
        ):
            continue

        match_time = datetime.fromisoformat(
            match["datetime"]
        )

        # Not today's match
        if match_time.date() != now.date():
            continue

        # Match already started
        if match_time <= now:
            continue

        text = (

            "🔥 بازی امروز\n\n"

            f"⚽️ {match['home']}\n"
            "🆚\n"
            f"⚽️ {match['away']}\n\n"

            "📅 امروز\n"
            f"🕐 {match_time.strftime('%H:%M')}\n"

            "🇮🇷 به وقت ایران"
        )

        send_message(
            GROUP_CHAT_ID,
            text
        )

        match["sent_today"] = True

        changed = True

    return changed


# =========================
# CHECK ALL MATCHES
# =========================

def check_matches():

    now = datetime.now(
        TEHRAN
    )

    matches = load_json(
        MATCHES_FILE,
        []
    )

    changed = False

    if check_24_hour_notifications(
        now,
        matches
    ):

        changed = True

    if check_today_notifications(
        now,
        matches
    ):

        changed = True

    if changed:

        save_json(
            MATCHES_FILE,
            matches
        )


# =========================
# MAIN
# =========================

def main():

    process_updates()

    check_matches()


if __name__ == "__main__":

    main()
