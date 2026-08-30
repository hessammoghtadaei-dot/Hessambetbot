import os
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
BROWSERLESS_TOKEN = os.environ["BROWSERLESS_TOKEN"]

OWNER_ID = 174537663

TEHRAN = ZoneInfo("Asia/Tehran")

MATCHES_FILE = "matches.json"
STATE_FILE = "state.json"


# =========================================================
# TELEGRAM
# =========================================================

def telegram(method, data=None, files=None):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if files:

        boundary = "----HessamBetBoundary"

        body = bytearray()

        for name, value in (data or {}).items():

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

        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(
                data or {}
            ).encode()
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


# =========================================================
# JSON
# =========================================================

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


# =========================================================
# BROWSERLESS
# =========================================================

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


# =========================================================
# FOTMOB
# =========================================================

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

                teams.append({
                    "name": name,
                    "id": team_id
                })

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
            (
                "https://images.fotmob.com/"
                "image_resources/logo/teamlogo/"
                f"{home['id']}.png"
            ),

        "away_logo":
            (
                "https://images.fotmob.com/"
                "image_resources/logo/teamlogo/"
                f"{away['id']}.png"
            ),

        "datetime":
            match_time.isoformat(),

        "sent_24h":
            False,

        "sent_today":
            False
    }


# =========================================================
# IMAGE HELPERS
# =========================================================

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

        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]

    else:

        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for path in paths:

        if os.path.exists(path):

            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()


def rounded_rectangle(
    draw,
    box,
    radius,
    fill,
    outline=None,
    width=1
):

    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width
    )


# =========================================================
# MATCH CARD
# =========================================================

def create_match_card(match, mode):

    width = 1200
    height = 800

    # -----------------------------------------------------
    # BACKGROUND
    # -----------------------------------------------------

    image = Image.new(
        "RGB",
        (width, height),
        (11, 14, 22)
    )

    draw = ImageDraw.Draw(
        image
    )

    # Subtle background circles

    glow = Image.new(
        "RGBA",
        (width, height),
        (0, 0, 0, 0)
    )

    glow_draw = ImageDraw.Draw(
        glow
    )

    glow_draw.ellipse(
        (-250, -200, 500, 550),
        fill=(35, 80, 160, 70)
    )

    glow_draw.ellipse(
        (850, 350, 1450, 950),
        fill=(110, 45, 160, 50)
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(90)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        glow
    ).convert("RGB")

    draw = ImageDraw.Draw(
        image
    )

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    draw.text(
        (600, 48),
        "HessamBet",
        font=get_font(
            56,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    if mode == "24h":

        title = "24 HOURS TO GO"

    else:

        title = "TODAY'S MATCH"

    draw.text(
        (600, 112),
        title,
        font=get_font(
            25,
            True
        ),
        anchor="ma",
        fill=(180, 190, 210)
    )

    # -----------------------------------------------------
    # MAIN MATCH PANEL
    # -----------------------------------------------------

    rounded_rectangle(
        draw,
        (70, 165, 1130, 690),
        36,
        (21, 26, 38),
        outline=(55, 64, 82),
        width=2
    )

    # -----------------------------------------------------
    # TEAM LOGOS
    # -----------------------------------------------------

    try:

        home_logo = download_image(
            match["home_logo"]
        )

        home_logo.thumbnail(
            (210, 210)
        )

        away_logo = download_image(
            match["away_logo"]
        )

        away_logo.thumbnail(
            (210, 210)
        )

        # Logo circles / panels

        rounded_rectangle(
            draw,
            (150, 225, 410, 485),
            30,
            (29, 35, 50)
        )

        rounded_rectangle(
            draw,
            (790, 225, 1050, 485),
            30,
            (29, 35, 50)
        )

        image.paste(
            home_logo,
            (
                280 - home_logo.width // 2,
                355 - home_logo.height // 2
            ),
            home_logo
        )

        image.paste(
            away_logo,
            (
                920 - away_logo.width // 2,
                355 - away_logo.height // 2
            ),
            away_logo
        )

    except Exception as error:

        print(
            "Logo error:",
            error
        )

    # -----------------------------------------------------
    # VS
    # -----------------------------------------------------

    draw.text(
        (600, 355),
        "VS",
        font=get_font(
            48,
            True
        ),
        anchor="mm",
        fill=(255, 255, 255)
    )

    # -----------------------------------------------------
    # TEAM NAMES
    # -----------------------------------------------------

    draw.text(
        (280, 535),
        match["home"],
        font=get_font(
            32,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    draw.text(
        (920, 535),
        match["away"],
        font=get_font(
            32,
            True
        ),
        anchor="ma",
        fill=(255, 255, 255)
    )

    # -----------------------------------------------------
    # MATCH DATE / TIME
    # -----------------------------------------------------

    match_time = datetime.fromisoformat(
        match["datetime"]
    )

    date_text = match_time.strftime(
        "%d/%m/%Y"
    )

    time_text = match_time.strftime(
        "%H:%M"
    )

    rounded_rectangle(
        draw,
        (365, 585, 835, 665),
        25,
        (29, 35, 50)
    )

    draw.text(
        (600, 612),
        date_text,
        font=get_font(
            23,
            True
        ),
        anchor="mm",
        fill=(210, 215, 225)
    )

    draw.text(
        (600, 645),
        time_text,
        font=get_font(
            27,
            True
        ),
        anchor="mm",
        fill=(255, 255, 255)
    )

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------

    draw.text(
        (600, 740),
        "IRAN TIME  •  HessamBet",
        font=get_font(
            20,
            True
        ),
        anchor="mm",
        fill=(125, 135, 155)
    )

    # -----------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------

    output = BytesIO()

    image.save(
        output,
        "PNG",
        optimize=True
    )

    return output.getvalue()


# =========================================================
# MATCH STORAGE
# =========================================================

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


# =========================================================
# TELEGRAM UPDATES
# =========================================================

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

        # Commands only from private chat

        if chat.get(
            "type"
        ) != "private":

            continue

        # Only owner

        if message.get(
            "from",
            {}
        ).get(
            "id"
        ) != OWNER_ID:

            continue

        text = message.get(
            "text",
            ""
        ).strip()

        # -------------------------------------------------
        # START
        # -------------------------------------------------

        if text == "/start":

            send_message(
                chat["id"],
                "⚽ HessamBet فعال است."
            )

            continue

        # -------------------------------------------------
        # TEST 24H
        # -------------------------------------------------

        if text == "/test24":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if not matches:

                send_message(
                    chat["id"],
                    "❌ هیچ بازی‌ای برای تست وجود ندارد."
                )

                continue

            try:

                image = create_match_card(
                    matches[-1],
                    "24h"
                )

                send_image(
                    GROUP_CHAT_ID,
                    image,
                    "🧪 تست کارت اعلان ۲۴ ساعته"
                )

                send_message(
                    chat["id"],
                    "✅ تست کارت ۲۴ ساعته ارسال شد."
                )

            except Exception as error:

                print(
                    "TEST24 ERROR:",
                    error
                )

                send_message(
                    chat["id"],
                    "❌ خطا در ساخت کارت تست."
                )

            continue

        # -------------------------------------------------
        # TEST TODAY
        # -------------------------------------------------

        if text == "/testtoday":

            matches = load_json(
                MATCHES_FILE,
                []
            )

            if not matches:

                send_message(
                    chat["id"],
                    "❌ هیچ بازی‌ای برای تست وجود ندارد."
                )

                continue

            try:

                image = create_match_card(
                    matches[-1],
                    "today"
                )

                send_image(
                    GROUP_CHAT_ID,
                    image,
                    "🧪 تست کارت بازی امروز"
                )

                send_message(
                    chat["id"],
                    "✅ تست کارت بازی امروز ارسال شد."
                )

            except Exception as error:

                print(
                    "TESTTODAY ERROR:",
                    error
                )

                send_message(
                    chat["id"],
                    "❌ خطا در ساخت کارت تست."
                )

            continue

        # -------------------------------------------------
        # FOTMOB LINK
        # -------------------------------------------------

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
                    "FOTMOB ERROR:",
                    error
                )

                match = None

            if not match:

                send_message(
                    chat["id"],
                    "❌ اطلاعات کامل بازی از FotMob دریافت نشد."
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


# =========================================================
# AUTOMATIC NOTIFICATIONS
# =========================================================

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

        # -------------------------------------------------
        # 24 HOURS BEFORE
        # -------------------------------------------------

        notification_time = (
            match_time - timedelta(
                hours=24
            )
        )

        if (
            not match.get(
                "sent_24h",
                False
            )
            and
            notification_time <= now
            and
            now < match_time
        ):

            try:

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

            except Exception as error:

                print(
                    "24H NOTIFICATION ERROR:",
                    error
                )

        # -------------------------------------------------
        # TODAY
        # -------------------------------------------------

        if (
            not match.get(
                "sent_today",
                False
            )
            and
            match_time.date()
            == now.date()
            and
            match_time > now
            and
            now.hour == 12
            and
            now.minute < 5
        ):

            try:

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

            except Exception as error:

                print(
                    "TODAY NOTIFICATION ERROR:",
                    error
                )

    if changed:

        save_json(
            MATCHES_FILE,
            matches
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print("HessamBet starting...")

    process_updates()

    check_notifications()

    print("HessamBet finished.")


if __name__ == "__main__":

    main()
