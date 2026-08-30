import os
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


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

def telegram(method, data=None, files=None):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if files:

        boundary = "----HessamBetBoundary"
        body = bytearray()

        for name, value in data.items():

            body.extend(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n".encode()
            )

        for name, filename, content in files:

            body.extend(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: image/png\r\n\r\n".encode()
            )

            body.extend(content)
            body.extend(b"\r\n")

        body.extend(
            f"--{boundary}--\r\n".encode()
        )

        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type":
                f"multipart/form-data; boundary={boundary}"
            }
        )

    else:

        encoded = urllib.parse.urlencode(
            data or {}
        ).encode()

        request = urllib.request.Request(
            url,
            data=encoded
        )

    with urllib.request.urlopen(
        request,
        timeout=60
    ) as response:

        return json.loads(
            response.read().decode()
        )


def send_message(chat_id, text):

    return telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text
        }
    )


def send_image(chat_id, image_bytes, caption):

    return telegram(
        "sendPhoto",
        {
            "chat_id": chat_id,
            "caption": caption
        },
        [
            (
                "photo",
                "hessambet.png",
                image_bytes
            )
        ]
    )


# =========================
# JSON
# =========================

def load_json(filename, default):

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return default


def save_json(filename, data):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

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
    }).encode()

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

    result = re.search(
        r"fotmob\.com/match/(\d+)",
        url
    )

    if result:
        return result.group(1)

    return None


def extract_next_data(html):

    result = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>'
        r'(.*?)</script>',
        html,
        re.DOTALL
    )

    if not result:
        return None

    try:

        return json.loads(
            result.group(1)
        )

    except Exception:

        return None


def find_team_objects(obj):

    teams = []

    if isinstance(obj, dict):

        if (
            ("name" in obj or "shortName" in obj)
            and
            ("id" in obj or "teamId" in obj)
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

                teams.append(
                    {
                        "name": name,
                        "id": team_id
                    }
                )

        for value in obj.values():

            teams.extend(
                find_team_objects(value)
            )

    elif isinstance(obj, list):

        for value in obj:

            teams.extend(
                find_team_objects(value)
            )

    return teams


def find_value(obj, keys):

    if isinstance(obj, dict):

        for key in keys:

            if key in obj:

                value = obj[key]

                if value is not None:

                    return value

        for value in obj.values():

            result = find_value(
                value,
                keys
            )

            if result is not None:

                return result

    elif isinstance(obj, list):

        for value in obj:

            result = find_value(
                value,
                keys
            )

            if result is not None:

                return result

    return None


def extract_match(html, match_id):

    data = extract_next_data(html)

    if not data:
        return None

    teams = find_team_objects(data)

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

    timestamp = find_value(
        data,
        [
            "startTimestamp",
            "startTime",
            "timestamp"
        ]
    )

    match_time = None

    if isinstance(
        timestamp,
        (int, float)
    ):

        try:

            match_time = datetime.fromtimestamp(
                timestamp,
                ZoneInfo("UTC")
            ).astimezone(
                TEHRAN
            )

        except Exception:
            pass

    if match_time is None:

        date_value = find_value(
            data,
            [
                "utcTime",
                "date"
            ]
        )

        if isinstance(
            date_value,
            str
        ):

            try:

                match_time = datetime.fromisoformat(
                    date_value.replace(
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

        "match_id":
            str(match_id),

        "home":
            home["name"],

        "away":
            away["name"],

        "home_id":
            home["id"],

        "away_id":
            away["id"],

        "home_logo":
            f"https://images.fotmob.com/"
            f"image_resources/logo/teamlogo/"
            f"{home['id']}.png",

        "away_logo":
            f"https://images.fotmob.com/"
            f"image_resources/logo/teamlogo/"
            f"{away['id']}.png",

        "datetime":
            match_time.isoformat(),

        "sent_24h":
            False,

        "sent_today":
            False
    }


# =========================
# IMAGE
# =========================

def download_image(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return Image.open(
            BytesIO(
                response.read()
            )
        ).convert("RGBA")


def get_font(size, bold=False):

    if bold:

        path = (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
        )

    else:

        path = (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        )

    return ImageFont.truetype(
        path,
        size
    )


def create_match_card(match, mode):

    width = 1200
    height = 750

    image = Image.new(
        "RGB",
        (width, height),
        (18, 20, 28)
    )

    draw = ImageDraw.Draw(
        image
    )

    # HEADER

    draw.text(
        (600, 50),
        "HessamBet",
        font=get_font(
            58,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    if mode == "24h":

        subtitle = "24 HOURS TO GO"

    else:

        subtitle = "TODAY'S MATCH"

    draw.text(
        (600, 125),
        subtitle,
        font=get_font(
            28,
            True
        ),
        anchor="ma",
        fill=(210, 210, 210)
    )

    # LOGOS

    home_logo = download_image(
        match["home_logo"]
    )

    away_logo = download_image(
        match["away_logo"]
    )

    home_logo.thumbnail(
        (220, 220)
    )

    away_logo.thumbnail(
        (220, 220)
    )

    image.paste(
        home_logo,
        (
            270 - home_logo.width // 2,
            220
        ),
        home_logo
    )

    image.paste(
        away_logo,
        (
            930 - away_logo.width // 2,
            220
        ),
        away_logo
    )

    # VS

    draw.text(
        (600, 325),
        "VS",
        font=get_font(
            48,
            True
        ),
        anchor="mm",
        fill=(255, 255, 255)
    )

    # TEAMS

    draw.text(
        (270, 490),
        match["home"],
        font=get_font(
            34,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    draw.text(
        (930, 490),
        match["away"],
        font=get_font(
            34,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    # DATE

    match_time = datetime.fromisoformat(
        match["datetime"]
    )

    draw.text(
        (600, 585),
        match_time.strftime(
            "%d/%m/%Y   •   %H:%M"
        ),
        font=get_font(
            32,
            True
        ),
        anchor="mm",
        fill=(235, 235, 235)
    )

    draw.text(
        (600, 650),
        "IRAN TIME",
        font=get_font(
            23
        ),
        anchor="mm",
        fill=(170, 170, 170)
    )

    output = BytesIO()

    image.save(
        output,
        "PNG"
    )

    return output.getvalue()


# =========================
# ADD MATCH
# =========================

def add_match(match):

    matches = load_json(
        MATCHES_FILE,
        []
    )

    for old in matches:

        if str(
            old.get(
                "match_id",
                ""
            )
        ) == str(
            match["match_id"]
        ):

            return False

    matches.append(match)

    save_json(
        MATCHES_FILE,
        matches
    )

    return True


# =========================
# TELEGRAM COMMANDS
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

    response = telegram(
        "getUpdates",
        {
            "offset": offset,
            "timeout": 1
        }
    )

    for update in response.get(
        "result",
        []
    ):

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

        if message.get(
            "from",
            {}
        ).get("id") != OWNER_ID:

            continue

        text = message.get(
            "text",
            ""
        ).strip()

        # START

        if text == "/start":

            send_message(
                chat["id"],
                "⚽ HessamBet فعال است."
            )

            continue

        # TEST 24

        if text == "/test24":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if matches:

                image = create_match_card(
                    matches[-1],
                    "24h"
                )

                send_image(
                    GROUP_CHAT_ID,
                    image,
                    "🧪 تست اعلان ۲۴ ساعته"
                )

                send_message(
                    chat["id"],
                    "✅ تست ارسال شد."
                )

            continue

        # TEST TODAY

        if text == "/testtoday":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if matches:

                image = create_match_card(
                    matches[-1],
                    "today"
                )

                send_image(
                    GROUP_CHAT_ID,
                    image,
                    "🧪 تست اعلان بازی امروز"
                )

                send_message(
                    chat["id"],
                    "✅ تست ارسال شد."
                )

            continue

        # FOTMOB LINK

        if "fotmob.com/match/" in text:

            match_id = get_match_id(
                text
            )

            if not match_id:
                continue

            send_message(
                chat["id"],
                "⏳ دریافت اطلاعات بازی..."
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
                    "ERROR:",
                    error
                )

                match = None

            if not match:

                send_message(
                    chat["id"],
                    "❌ اطلاعات کامل بازی دریافت نشد."
                )

                continue

            if add_match(match):

                send_message(
                    chat["id"],
                    "✅ بازی دریافت شد."
                )

            else:

                send_message(
                    chat["id"],
                    "ℹ️ این بازی قبلاً اضافه شده."
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

        # ONLY REAL 24-HOUR NOTIFICATION

        if (

            not match.get(
                "sent_24h",
                False
            )

            and

            match_time - timedelta(
                hours=24
            )

            <= now

            < match_time

        ):

            image = create_match_card(
                match,
                "24h"
            )

            send_image(
                GROUP_CHAT_ID,
                image,
                "⏳ ۲۴ ساعت تا شروع بازی"
            )

            match["sent_24h"] = True

            changed = True

        # TODAY

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

            now.minute < 5

            and

            match_time > now

        ):

            image = create_match_card(
                match,
                "today"
            )

            send_image(
                GROUP_CHAT_ID,
                image,
                "🔥 بازی امروز"
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
