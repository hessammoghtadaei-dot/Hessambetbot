import os
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
BROWSERLESS_TOKEN = os.environ["BROWSERLESS_TOKEN"]

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


def send_photo(chat_id, photo, caption=None):

    data = {
        "chat_id": chat_id,
        "photo": photo
    }

    if caption:
        data["caption"] = caption

    telegram(
        "sendPhoto",
        data
    )


# =========================
# FILES
# =========================

def load_json(filename, default):

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filename, data):

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================
# BROWSERLESS
# =========================

def browserless_html(url):

    endpoint = (
        "https://production-sfo.browserless.io/content"
        f"?token={urllib.parse.quote(BROWSERLESS_TOKEN)}"
    )

    payload = json.dumps({
        "url": url,
        "waitForTimeout": 5000
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=60
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


# =========================
# FOTMOB
# =========================

def get_match_id(url):

    match = re.search(
        r"fotmob\.com/match/(\d+)",
        url
    )

    if not match:
        return None

    return match.group(1)


def extract_next_data(html):

    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>'
        r'(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        return None

    try:
        return json.loads(
            match.group(1)
        )
    except Exception:
        return None


def find_key(obj, key):

    if isinstance(obj, dict):

        if key in obj:
            return obj[key]

        for value in obj.values():

            result = find_key(
                value,
                key
            )

            if result is not None:
                return result

    elif isinstance(obj, list):

        for value in obj:

            result = find_key(
                value,
                key
            )

            if result is not None:
                return result

    return None


def find_team_objects(obj):

    found = []

    if isinstance(obj, dict):

        if (
            ("name" in obj or "shortName" in obj)
            and
            (
                "id" in obj
                or "teamId" in obj
            )
        ):

            name = (
                obj.get("name")
                or obj.get("shortName")
            )

            team_id = (
                obj.get("id")
                or obj.get("teamId")
            )

            if name and team_id:

                found.append({
                    "name": name,
                    "id": team_id,
                    "logo": (
                        obj.get("logo")
                        or obj.get("logoUrl")
                    )
                })

        for value in obj.values():

            found.extend(
                find_team_objects(value)
            )

    elif isinstance(obj, list):

        for value in obj:

            found.extend(
                find_team_objects(value)
            )

    return found


def team_logo(team):

    if team.get("logo"):
        return team["logo"]

    team_id = team.get("id")

    if not team_id:
        return None

    return (
        "https://images.fotmob.com/"
        "image_resources/logo/teamlogo/"
        f"{team_id}.png"
    )


def extract_timestamp(data):

    possible_keys = [
        "startTimestamp",
        "startTime",
        "utcTime",
        "timestamp"
    ]

    for key in possible_keys:

        value = find_key(
            data,
            key
        )

        if value is None:
            continue

        try:

            if isinstance(
                value,
                (int, float)
            ):

                return datetime.fromtimestamp(
                    value,
                    tz=ZoneInfo("UTC")
                ).astimezone(
                    TEHRAN
                )

        except Exception:
            pass

    return None


def extract_match(html, match_id):

    data = extract_next_data(
        html
    )

    if not data:
        return None

    teams = find_team_objects(
        data
    )

    unique = []

    seen = set()

    for team in teams:

        key = (
            str(team["id"]),
            team["name"]
        )

        if key not in seen:

            seen.add(key)
            unique.append(team)

    if len(unique) < 2:
        return None

    home = unique[0]
    away = unique[1]

    match_time = extract_timestamp(
        data
    )

    if match_time is None:

        # Try ISO date strings
        date_match = re.search(
            r'"(?:startTime|utcTime|date)"\s*:\s*"'
            r'([^"]+)"',
            html
        )

        if date_match:

            try:

                match_time = datetime.fromisoformat(
                    date_match.group(1)
                    .replace(
                        "Z",
                        "+00:00"
                    )
                ).astimezone(
                    TEHRAN
                )

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

        "home_logo": team_logo(home),
        "away_logo": team_logo(away),

        "datetime": match_time.isoformat(),

        "sent_24h": False,
        "sent_today": False
    }


# =========================
# ADD MATCH
# =========================

def add_match(match):

    matches = load_json(
        MATCHES_FILE,
        []
    )

    for existing in matches:

        if str(
            existing.get("match_id", "")
        ) == str(
            match["match_id"]
        ):

            return False, len(matches)

    matches.append(match)

    save_json(
        MATCHES_FILE,
        matches
    )

    return True, len(matches)


# =========================
# SEND MATCH
# =========================

def send_match(match, mode):

    match_time = datetime.fromisoformat(
        match["datetime"]
    )

    if mode == "24h":

        title = "⏳ ۲۴ ساعت تا شروع مسابقه"

        date_text = match_time.strftime(
            "%d/%m/%Y"
        )

    else:

        title = "🔥 بازی امروز"

        date_text = "امروز"

    caption = (

        f"{title}\n\n"

        f"⚽️ {match['home']}\n"
        "🆚\n"
        f"⚽️ {match['away']}\n\n"

        f"📅 {date_text}\n"
        f"🕐 {match_time.strftime('%H:%M')}\n"

        "🇮🇷 به وقت ایران"
    )

    home_logo = match.get(
        "home_logo"
    )

    away_logo = match.get(
        "away_logo"
    )

    if home_logo:

        send_photo(
            GROUP_CHAT_ID,
            home_logo,
            caption
        )

    if away_logo:

        send_photo(
            GROUP_CHAT_ID,
            away_logo
        )

    if not home_logo and not away_logo:

        send_message(
            GROUP_CHAT_ID,
            caption
        )


# =========================
# TELEGRAM UPDATES
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

    try:

        response = telegram(
            "getUpdates",
            {
                "offset": offset,
                "timeout": 1
            }
        )

        updates = response.get(
            "result",
            []

        )

    except Exception:

        updates = []

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

        if chat.get(
            "type"
        ) != "private":

            continue

        user = message.get(
            "from",
            {}
        )

        if user.get(
            "id"
        ) != OWNER_ID:

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

                "لینک بازی FotMob را بفرست.\n\n"

                "مثال:\n"
                "https://www.fotmob.com/match/5868038\n\n"

                "تست‌ها:\n"
                "/test24\n"
                "/testtoday"
            )

            continue

        # =====================
        # TEST 24
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

            else:

                send_match(
                    matches[-1],
                    "24h"
                )

                send_message(
                    chat["id"],
                    "✅ تست ۲۴ ساعته ارسال شد."
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

            else:

                send_match(
                    matches[-1],
                    "today"
                )

                send_message(
                    chat["id"],
                    "✅ تست روز بازی ارسال شد."
                )

            continue

        # =====================
        # FOTMOB
        # =====================

        if "fotmob.com/match/" in text:

            match_id = get_match_id(
                text
            )

            if not match_id:

                send_message(
                    chat["id"],
                    "❌ لینک FotMob معتبر نیست."
                )

                continue

            send_message(
                chat["id"],
                "⏳ در حال دریافت اطلاعات بازی و لوگوها..."
            )

            try:

                html = browserless_html(
                    text
                )

                match = extract_match(
                    html,
                    match_id
                )

            except Exception as error:

                print(
                    "FotMob error:",
                    error
                )

                match = None

            if not match:

                send_message(

                    chat["id"],

                    "❌ اطلاعات بازی از FotMob استخراج نشد.\n\n"
                    f"Match ID: {match_id}"

                )

                continue

            added, total = add_match(
                match
            )

            if added:

                match_time = datetime.fromisoformat(
                    match["datetime"]
                )

                send_message(

                    chat["id"],

                    "✅ بازی اضافه شد.\n\n"

                    f"⚽️ {match['home']}\n"
                    f"🆚 {match['away']}\n\n"

                    f"📅 {match_time.strftime('%d/%m/%Y')}\n"
                    f"🕐 {match_time.strftime('%H:%M')}\n\n"

                    "🖼 لوگوی تیم‌ها دریافت شد.\n"
                    f"📋 مجموع بازی‌ها: {total}"

                )

            else:

                send_message(
                    chat["id"],
                    "ℹ️ این بازی قبلاً اضافه شده."
                )

            continue

        # =====================
        # INVALID
        # =====================

        send_message(

            chat["id"],

            "❌ فقط لینک بازی FotMob را بفرست."

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

        # 24 HOURS BEFORE
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

            send_match(
                match,
                "24h"
            )

            match["sent_24h"] = True

            changed = True

        # TODAY AT 12:00
        if (

            not match.get(
                "sent_today",
                False
            )

            and

            match_time.date()
            == now.date()

            and

            now.hour == 12

            and

            now.minute <= 4

            and

            match_time > now

        ):

            send_match(
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
