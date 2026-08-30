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


def send_message(chat_id, text):
    telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text
        }
    )


def
