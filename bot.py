import os
import json
import re
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


# =========================
# TELEGRAM
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


def send_photo(chat_id, photo, caption):

    telegram(
        "sendPhoto",
        {
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption
        }
    )


# =========================
# FILES
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
# FOTMOB
# =========================

def get_fotmob_match_id(url):

    match = re.search(
        r"fotmob\.com/match/(\d+)",
        url
    )

    if not match:
        return None

    return match.group(1)


def get_fotmob_match(match_id):

    urls = [
        f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
        f"https://www.fotmob.com/api/data/matchDetails?matchId={match_id}"
    ]

    for url in urls:

        try:

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                    "Mozilla/5.0"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

                if isinstance(data, dict):
                    return data

        except Exception:
            continue

    return None


def extract_team(data, side):

    team = data.get(side)

    if not isinstance(team, dict):
        return None

    team_id = (
        team.get("id")
        or team.get("teamId")
    )

    name = (
        team.get("name")
        or team.get("shortName")
        or team.get("longName")
    )

    logo = (
        team.get("logo")
        or team.get("logoUrl")
    )

    if not logo and team_id:

        logo = (
            f"https://images.fotmob.com/image_resources/"
            f"logo/teamlogo/{team_id}.png"
        )

    return {
        "id": team_id,
        "name": name,
        "logo": logo
    }


def extract_match_info(data, match_id):

    home = extract_team(
        data,
        "home"
    )

    away = extract_team(
        data,
        "away"
    )

    if not home or not away:
        return None

    # FotMob normally provides UTC timestamp
    timestamp = (
        data.get("startTime")
        or data.get("startTimestamp")
        or data.get("utcTime")
    )

    match_time = None

    if timestamp:

        try:

            if isinstance(timestamp, (int, float)):

                match_time = datetime.fromtimestamp(
                    timestamp,
                    tz=ZoneInfo("UTC")
                ).astimezone(TEHRAN)

        except Exception:
            match_time = None

    # Alternative: UTC ISO date
    if match_time is None:

        date_value = data.get("date")

        if date_value:

            try:

                match_time = datetime.fromisoformat(
                    date_value.replace(
                        "Z",
                        "+00:00"
                    )
                ).astimezone(TEHRAN)

            except Exception:
                pass

    if match_time is None:
        return None

    return {

        "match_id": str(match_id),

        "home": home["name"],
        "away": away["name"],

        "home_id": home["id"],
        "away_id": away["id"],

        "home_logo": home["logo"],
        "away_logo": away["logo"],

        "datetime": match_time.isoformat(),

        "sent_24h": False,
        "sent_today": False

    }


# =========================
# ADD MATCH
# =========================

def add_fotmob_match(match):

    matches = load_json(
        MATCHES_FILE,
        []
    )

    for existing in matches:

        if (
            str(existing.get("match_id", ""))
            == str(match["match_id"])
        ):

            return False, len(matches)

    matches.append(match)

    save_json(
        MATCHES_FILE,
        matches
    )

    return True, len(matches)


# =========================
# GET UPDATES
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
# MATCH MESSAGE
# =========================

def match_caption(match, mode):

    match_time = datetime.fromisoformat(
        match["datetime"]
    )

    if mode == "24h":

        title = "⏳ ۲۴ ساعت تا شروع مسابقه"

        date_text = (
            match_time.strftime("%d/%m/%Y")
        )

    else:

        title = "🔥 بازی امروز"

        date_text = "امروز"

    return (

        f"{title}\n\n"

        f"⚽️ {match['home']}\n"
        "🆚\n"
        f"⚽️ {match['away']}\n\n"

        f"📅 {date_text}\n"
        f"🕐 {match_time.strftime('%H:%M')}\n"

        "🇮🇷 به وقت ایران"

    )


# =========================
# SEND MATCH WITH LOGOS
# =========================

def send_match_to_group(match, mode):

    caption = match_caption(
        match,
        mode
    )

    home_logo = match.get(
        "home_logo"
    )

    away_logo = match.get(
        "away_logo"
    )

    # Try combined media group first
    if home_logo and away_logo:

        try:

            media = json.dumps(
                [
                    {
                        "type": "photo",
                        "media": home_logo,
                        "caption": caption
                    },
                    {
                        "type": "photo",
                        "media": away_logo
                    }
                ],
                ensure_ascii=False
            )

            telegram(
                "sendMediaGroup",
                {
                    "chat_id": GROUP_CHAT_ID,
                    "media": media
                }
            )

            return True

        except Exception:
            pass

    # Fallback to normal message
    send_message(
        GROUP_CHAT_ID,
        caption
    )

    return True


# =========================
# PROCESS TELEGRAM
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

        if chat.get("type") != "private":
            continue

        user = message.get(
            "from",
            {}
        )

        if user.get("id") != OWNER_ID:
            continue

        text = message.get(
            "text",
            ""
        ).strip()

        # =====================
        # START
        # =====================

        if text == "/start":

            send_message(

                chat["id"],

                "⚽️ Hessambetbot فعال است.\n\n"

                "فقط لینک بازی FotMob را بفرست.\n\n"

                "مثال:\n"
                "https://www.fotmob.com/match/5868038\n\n"

                "دستورات تست:\n"
                "/test24\n"
                "/testtoday"
            )

            continue

        # =====================
        # TEST 24 HOURS
        # =====================

        if text == "/test24":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if not matches:

                send_message(
                    chat["id"],
                    "❌ هیچ بازی ذخیره نشده."
                )

                continue

            match = matches[-1]

            send_match_to_group(
                match,
                "24h"
            )

            send_message(
                chat["id"],
                "✅ تست اعلان ۲۴ ساعته ارسال شد."
            )

            continue

        # =====================
        # TEST TODAY
        # =====================

        if text == "/testtoday":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if not matches:

                send_message(
                    chat["id"],
                    "❌ هیچ بازی ذخیره نشده."
                )

                continue

            match = matches[-1]

            send_match_to_group(
                match,
                "today"
            )

            send_message(
                chat["id"],
                "✅ تست اعلان روز بازی ارسال شد."
            )

            continue

        # =====================
        # FOTMOB LINK
        # =====================

        if "fotmob.com/match/" in text:

            match_id = get_fotmob_match_id(
                text
            )

            if not match_id:

                send_message(
                    chat["id"],
                    "❌ شناسه بازی از لینک پیدا نشد."
                )

                continue

            send_message(
                chat["id"],
                "⏳ دارم اطلاعات بازی و لوگوها را از FotMob می‌گیرم..."
            )

            data = get_fotmob_match(
                match_id
            )

            if not data:

                send_message(
                    chat["id"],
                    "❌ نتوانستم اطلاعات بازی را از FotMob دریافت کنم."
                )

                continue

            match = extract_match_info(
                data,
                match_id
            )

            if not match:

                send_message(
                    chat["id"],
                    "❌ اطلاعات کامل بازی از FotMob دریافت نشد."
                )

                continue

            added, total = add_fotmob_match(
                match
            )

            if added:

                send_message(

                    chat["id"],

                    "✅ بازی اضافه شد.\n\n"

                    f"⚽️ {match['home']}\n"
                    f"🆚 {match['away']}\n\n"

                    f"📅 {datetime.fromisoformat(match['datetime']).strftime('%d/%m/%Y')}\n"
                    f"🕐 {datetime.fromisoformat(match['datetime']).strftime('%H:%M')}\n\n"

                    f"📋 مجموع بازی‌ها: {total}"

                )

            else:

                send_message(
                    chat["id"],
                    "ℹ️ این بازی قبلاً اضافه شده."
                )

            continue

        # =====================
        # INVALID MESSAGE
        # =====================

        send_message(

            chat["id"],

            "❌ لینک FotMob معتبر نیست.\n\n"

            "لینک را به این شکل بفرست:\n"
            "https://www.fotmob.com/match/5868038"

        )

    save_json(
        STATE_FILE,
        state
    )


# =========================
# NOTIFICATIONS
# =========================

def check_notifications():

    now = datetime.now(
        TEHRAN
    )

    matches = load_json(
        MATCHES_FILE,
        []
    )

    changed = False

    for match in matches:

        try:

            match_time = datetime.fromisoformat(
                match["datetime"]
            )

        except Exception:

            continue

        # =====================
        # 24 HOURS BEFORE
        # =====================

        if (

            not match.get(
                "sent_24h",
                False
            )

            and

            now >= (
                match_time
                - timedelta(hours=24)
            )

            and

            now < match_time

        ):

            send_match_to_group(
                match,
                "24h"
            )

            match["sent_24h"] = True

            changed = True

        # =====================
        # MATCH DAY 12:00
        # =====================

        if (

            not match.get(
                "sent_today",
                False
            )

            and

            now.hour == 12

            and

            now.minute <= 4

            and

            match_time.date()
            == now.date()

            and

            match_time > now

        ):

            send_match_to_group(
                match,
                "today"
            )

            match["sent_today"] = True

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

    check_notifications()


if __name__ == "__main__":

    main()
