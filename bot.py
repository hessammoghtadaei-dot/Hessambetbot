import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = os.environ["GROUP_CHAT_ID"]

IRAN_TZ = ZoneInfo("Asia/Tehran")

MATCHES_FILE = "matches.json"
STATE_FILE = "state.json"


def telegram(method, data=None):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if data:
        encoded = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(url, data=encoded)
    else:
        request = urllib.request.Request(url)

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def load_json(filename, default):

    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filename, data):

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_matches(text):

    matches = []

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
            ).replace(tzinfo=IRAN_TZ)

        except ValueError:

            continue

        matches.append({
            "home": home.strip(),
            "away": away.strip(),
            "datetime": match_time.isoformat(),
            "sent_24h": False,
            "sent_today": False
        })

    return matches


def add_matches(new_matches):

    matches = load_json(MATCHES_FILE, [])

    added = 0

    for new_match in new_matches:

        duplicate = any(
            m["home"].lower() == new_match["home"].lower()
            and m["away"].lower() == new_match["away"].lower()
            and m["datetime"] == new_match["datetime"]
            for m in matches
        )

        if not duplicate:

            matches.append(new_match)
            added += 1

    save_json(MATCHES_FILE, matches)

    return added, len(matches)


def send_message(text):

    telegram(
        "sendMessage",
        {
            "chat_id": GROUP_CHAT_ID,
            "text": text
        }
    )


def get_updates(offset):

    data = {}

    if offset:
        data["offset"] = offset

    result = telegram("getUpdates", data)

    return result.get("result", [])


def process_updates():

    state = load_json(STATE_FILE, {"offset": 0})

    offset = state.get("offset", 0)

    updates = get_updates(offset)

    for update in updates:

        update_id = update["update_id"]

        state["offset"] = update_id + 1

        message = update.get("message")

        if not message:
            continue

        chat = message.get("chat", {})

        # فقط پیام خصوصی صاحب ربات
        if chat.get("type") != "private":
            continue

        text = message.get("text", "").strip()

        if text == "/start":

            telegram(
                "sendMessage",
                {
                    "chat_id": chat["id"],
                    "text":
                    "⚽️ Hessambetbot فعال است.\n\n"
                    "بازی‌ها را به این شکل بفرست:\n\n"
                    "Real Madrid - Barcelona | 31/08/2026 | 23:00\n"
                    "Liverpool - Arsenal | 01/09/2026 | 22:30\n\n"
                    "هر بازی در یک خط."
                }
            )

            continue

        new_matches = parse_matches(text)

        if not new_matches:

            telegram(
                "sendMessage",
                {
                    "chat_id": chat["id"],
                    "text":
                    "❌ قالب بازی قابل تشخیص نیست.\n\n"
                    "نمونه:\n"
                    "Real Madrid - Barcelona | 31/08/2026 | 23:00"
                }
            )

            continue

        added, total = add_matches(new_matches)

        telegram(
            "sendMessage",
            {
                "chat_id": chat["id"],
                "text":
                f"✅ {added} بازی اضافه شد.\n"
                f"📋 مجموع بازی‌های ذخیره‌شده: {total}"
            }
        )

    save_json(STATE_FILE, state)


def check_matches():

    now = datetime.now(IRAN_TZ)

    matches = load_json(MATCHES_FILE, [])

    changed = False

    for match in matches:

        match_time = datetime.fromisoformat(
            match["datetime"]
        )

        hours_left = (
            match_time - now
        ).total_seconds() / 3600

        # ----------------------------
        # 24 hours before
        # ----------------------------

        if (
            23.0 <= hours_left <= 24.1
            and not match["sent_24h"]
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

            send_message(text)

            match["sent_24h"] = True

            changed = True

        # ----------------------------
        # Match day
        # ----------------------------

        if (
            match_time.date() == now.date()
            and match_time > now
            and not match["sent_today"]
        ):

            text = (
                "🔥 بازی امروز\n\n"
                f"⚽️ {match['home']}\n"
                "🆚\n"
                f"⚽️ {match['away']}\n\n"
                f"📅 امروز\n"
                f"🕐 {match_time.strftime('%H:%M')}\n"
                "🇮🇷 به وقت ایران"
            )

            send_message(text)

            match["sent_today"] = True

            changed = True

    if changed:

        save_json(MATCHES_FILE, matches)


def main():

    process_updates()

    check_matches()


if __name__ == "__main__":

    main()
