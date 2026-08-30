import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
OWNER_ID = 174537663

TEHRAN = ZoneInfo("Asia/Tehran")

MATCHES_FILE = "matches.json"
STATE_FILE = "state.json"


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


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def parse_matches(text):
    result = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = [x.strip() for x in line.split("|")]

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
            ).replace(tzinfo=TEHRAN)
        except ValueError:
            continue

        result.append({
            "home": home,
            "away": away,
            "datetime": match_time.isoformat(),
            "sent_24h": False,
            "sent_today": False
        })

    return result


def add_matches(new_matches):
    matches = load_json(MATCHES_FILE, [])
    added = 0

    for new_match in new_matches:
        duplicate = any(
            item["home"].lower() == new_match["home"].lower()
            and item["away"].lower() == new_match["away"].lower()
            and item["datetime"] == new_match["datetime"]
            for item in matches
        )

        if not duplicate:
            matches.append(new_match)
            added += 1

    save_json(MATCHES_FILE, matches)

    return added, len(matches)


def process_updates():

    state = load_json(
        STATE_FILE,
        {"offset": 0}
    )

    offset = state.get("offset", 0)

    data = {"timeout": 1}

    if offset:
        data["offset"] = offset

    updates = telegram(
        "getUpdates",
        data
    ).get("result", [])

    for update in updates:

        state["offset"] = update["update_id"] + 1

        message = update.get("message")

        if not message:
            continue

        chat = message.get("chat", {})

        if chat.get("type") != "private":
            continue

        user = message.get("from", {})

        if user.get("id") != OWNER_ID:
            continue

        text = message.get("text", "").strip()

        if text == "/start":

            send_message(
                chat["id"],
                "⚽️ Hessambetbot فعال است.\n\n"
                "فرمت ارسال بازی:\n\n"
                "Real Madrid - Barcelona | 31/08/2026 | 23:00"
            )

            continue

        new_matches = parse_matches(text)

        if not new_matches:

            send_message(
                chat["id"],
                "❌ فرمت بازی اشتباه است."
            )

            continue

        added, total = add_matches(new_matches)

        send_message(
            chat["id"],
            f"✅ {added} بازی اضافه شد.\n"
            f"📋 مجموع بازی‌ها: {total}"
        )

    save_json(
        STATE_FILE,
        state
    )


def check_notifications():

    now = datetime.now(TEHRAN)

    matches = load_json(
        MATCHES_FILE,
        []
    )

    changed = False

    for match in matches:

        match_time = datetime.fromisoformat(
            match["datetime"]
        )

        # 24 hours before
        if (
            not match.get("sent_24h", False)
            and now >= match_time - timedelta(hours=24)
            and now < match_time
        ):

            send_message(
                GROUP_CHAT_ID,
                "⏳ ۲۴ ساعت تا شروع مسابقه\n\n"
                f"⚽️ {match['home']}\n"
                f"🆚\n"
                f"⚽️ {match['away']}\n\n"
                f"📅 {match_time.strftime('%d/%m/%Y')}\n"
                f"🕐 {match_time.strftime('%H:%M')}\n"
                "🇮🇷 به وقت ایران"
            )

            match["sent_24h"] = True
            changed = True

        # Match day at 12:00
        if (
            not match.get("sent_today", False)
            and now.hour == 12
            and now.minute <= 4
            and match_time.date() == now.date()
            and match_time > now
        ):

            send_message(
                GROUP_CHAT_ID,
                "🔥 بازی امروز\n\n"
                f"⚽️ {match['home']}\n"
                f"🆚\n"
                f"⚽️ {match['away']}\n\n"
                f"🕐 {match_time.strftime('%H:%M')}\n"
                "🇮🇷 به وقت ایران"
            )

            match["sent_today"] = True
            changed = True

    if changed:
        save_json(MATCHES_FILE, matches)


def main():
    process_updates()
    check_notifications()


if __name__ == "__main__":
    main()
