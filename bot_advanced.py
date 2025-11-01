# bot_advanced.py
"""
AstroLuna Advanced — на базе рабочего bot.py, с синастрией, TZ-поддержкой и защитой от ошибок.
Требует .env с BOT_TOKEN_SYNASTRY (или BOT_TOKEN).
Зависимости: python-telegram-bot matplotlib pyswisseph python-dotenv pytz tzdata
"""

import os
import math
import re
import traceback
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
import matplotlib.pyplot as plt
import swisseph as swe
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- Load token ----------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN_SYNASTRY") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ В .env не найден BOT_TOKEN_SYNASTRY или BOT_TOKEN")

print(f"Using token from: {'BOT_TOKEN_SYNASTRY' if os.getenv('BOT_TOKEN_SYNASTRY') else 'BOT_TOKEN'}")

# ---------------- Constants (from your working bot) ----------------
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
}

# Russian zodiac names (same as your working bot)
ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
]

SIGN_DESCRIPTIONS = {
    "Sun": {
        "Овен": "активная, энергичная и решительная личность",
        "Телец": "спокойная, надёжная и практичная личность",
        "Близнецы": "умная, подвижная и любознательная личность",
        "Рак": "эмоциональная и заботливая личность",
        "Лев": "уверенная, щедрая и яркая личность",
        "Дева": "внимательная, логичная и аккуратная личность",
        "Весы": "уравновешенная и дипломатичная личность",
        "Скорпион": "глубокая, страстная и сильная личность",
        "Стрелец": "искренняя, философская и свободолюбивая личность",
        "Козерог": "ответственная, дисциплинированная личность",
        "Водолей": "независимая, оригинальная и гуманная личность",
        "Рыбы": "интуитивная, добрая и чувствительная личность",
    }
}

# Mapping planet English->Cyrillic for image labels
PLANET_RU = {
    "Sun": "Солнце",
    "Moon": "Луна",
    "Mercury": "Меркурий",
    "Venus": "Венера",
    "Mars": "Марс",
    "Jupiter": "Юпитер",
    "Saturn": "Сатурн",
}

# City -> tz mapping (extendable). Accepts user-friendly Russian names.
CITY_TIMEZONE = {
    "Костанай": "Asia/Almaty",
    "Алматы": "Asia/Almaty",
    "Астана": "Asia/Nur-Sultan",
    "Нур-Султан": "Asia/Nur-Sultan",
    "Москва": "Europe/Moscow",
    "Санкт-Петербург": "Europe/Moscow",
    "Лондон": "Europe/London",
    "Нью-Йорк": "America/New_York",
    "Karachi": "Asia/Karachi",
    "Карачи": "Asia/Karachi",
    # add more mappings as you like
}

MAX_CAPTION = 1000  # safe limit for splitting captions

# ---------------- Utility helpers ----------------
def clean_number(s):
    return re.sub(r"\D", "", s)

def get_zodiac_sign(degree):
    index = int(degree // 30) % 12
    return ZODIAC_SIGNS[index]

def safe_calc_ut(jd, code):
    """
    Safe wrapper around swe.calc_ut that handles different return formats.
    Returns longitude (float) or None.
    """
    try:
        res = swe.calc_ut(jd, code)
        # res often is a tuple/list: ([lon, lat, dist], retflag) or (lon, lat, dist)
        if isinstance(res, (list, tuple)):
            first = res[0]
            if isinstance(first, (list, tuple)):
                lon = first[0]
            else:
                # first might already be longitude
                lon = first
        else:
            lon = float(res)
        return float(lon)
    except Exception as e:
        # don't raise here — caller will mark as None
        print(f"⚠️ swisseph calc_ut error: {e}")
        return None

def parse_input_flexible(text: str):
    """
    Flexible parse for: Name, DD.MM.YYYY, HH:MM, City
    Returns (name, date_str, time_str, city) or raises ValueError.
    """
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 4:
        # try semicolon or dot+space splitting as fallback
        parts = [p.strip() for p in re.split(r"[;,]\s*", text)]
    if len(parts) < 4:
        # last resort: try to find date/time tokens
        tokens = text.split()
        date_token = None
        time_token = None
        for i, t in enumerate(tokens):
            if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", t):
                date_token = t
                if i + 1 < len(tokens) and re.match(r"^\d{1,2}:\d{2}$", tokens[i+1]):
                    time_token = tokens[i+1]
                break
        if date_token and time_token:
            name = " ".join(tokens[:i])
            city = " ".join(tokens[i+2:]) if len(tokens) > i+2 else ""
            return name.strip() or "Неизвестно", date_token, time_token, city.strip() or "Неизвестно"
        raise ValueError("Неверный формат. Используйте: Имя, ДД.MM.ГГГГ, ЧЧ:ММ, Город")
    # join extra parts of city in case user had commas inside city name
    name = parts[0]
    date_s = parts[1]
    time_s = parts[2]
    city = ", ".join(parts[3:]).strip()
    return name, date_s, time_s, city

def convert_local_to_jd_with_tz(date_s: str, time_s: str, city: str):
    """
    If city is in CITY_TIMEZONE -> use ZoneInfo to convert local to UTC and produce JD.
    Otherwise return None (caller can fallback to naive decimal hour).
    """
    try:
        tz_name = CITY_TIMEZONE.get(city)
        if not tz_name:
            # try if user provided tz directly
            tz_name = city if city in pytz.all_timezones else None
        if not tz_name:
            return None  # caller will use naive method
        # parse date/time
        day, month, year = map(int, date_s.split("."))
        hour, minute = map(int, time_s.split(":"))
        try:
            tzinfo = ZoneInfo(tz_name)
        except Exception:
            tzinfo = pytz.timezone(tz_name)
        local_dt = datetime(year, month, day, hour, minute, tzinfo=tzinfo)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        dec_hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
        jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, dec_hour)
        return jd
    except Exception as e:
        print("convert_local_to_jd_with_tz error:", e)
        return None

# ---------------- Core: generate chart & summary ----------------
def generate_natal_chart_and_summary(date_str, time_str, city):
    """
    Returns (BytesIO image, summary_text)
    Behavior:
    - If city in CITY_TIMEZONE or user supplied tz, convert local->UTC before julday.
    - Else fallback to original naive behavior used in your working bot (no TZ): julday(year, month, day, decimal_hour)
    """
    # parse date/time numbers
    try:
        day = int(clean_number(date_str.split(".")[0]))
        month = int(clean_number(date_str.split(".")[1]))
        year = int(clean_number(date_str.split(".")[2]))
        hour = int(clean_number(time_str.split(":")[0]))
        minute = int(clean_number(time_str.split(":")[1]))
    except Exception:
        raise ValueError("Неверный формат даты или времени. Используйте ДД.MM.YYYY и HH:MM")

    # try tz-aware julday
    jd = convert_local_to_jd_with_tz(date_str, time_str, city)
    if jd is None:
        # fallback: original naive decimal hour, to preserve old bot behavior
        decimal_hour = hour + minute / 60.0
        jd = swe.julday(year, month, day, decimal_hour)

    planet_positions = {}
    planet_signs = {}
    for name, code in PLANETS.items():
        lon = safe_calc_ut(jd, code)
        if lon is None:
            # mark None
            planet_positions[name] = None
            planet_signs[name] = None
        else:
            lon = lon % 360
            planet_positions[name] = lon
            planet_signs[name] = get_zodiac_sign(lon)

    # --- Draw chart (matplotlib) ---
    # Use matplotlib's DejaVu Sans (default) which supports Cyrillic.
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'aspect': 'equal'})
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    circle = plt.Circle((0, 0), 1, color='lightgrey', fill=False, linewidth=2)
    ax.add_artist(circle)

    # zodiac sector lines & labels
    for i in range(12):
        ang = (i * 30) / 360 * 2 * math.pi
        x = math.cos(ang)
        y = math.sin(ang)
        ax.plot([0, x], [0, y], color='lightgray', linewidth=0.8)
        sx = 1.08 * math.cos(ang)
        sy = 1.08 * math.sin(ang)
        ax.text(sx, sy, ZODIAC_SIGNS[i], fontsize=10, ha='center', va='center')

    # planets — plot and Cyrillic labels
    for eng_name, lon in planet_positions.items():
        label = PLANET_RU.get(eng_name, eng_name)
        if lon is None:
            continue
        ang = math.radians(lon)
        x = 0.78 * math.cos(ang)
        y = 0.78 * math.sin(ang)
        ax.plot(x, y, 'o', markersize=8)
        # label a bit outside
        ax.text(x * 1.18, y * 1.18, f"{label}\n{lon:.1f}°", fontsize=9, ha='center', va='center')

    ax.set_title(f"Натальная карта {date_str} {time_str}\n{city}", fontsize=12)
    ax.axis('off')

    bio = BytesIO()
    plt.savefig(bio, format='png', bbox_inches='tight', dpi=150)
    bio.seek(0)
    plt.close(fig)

    # --- Summary text (human-friendly) ---
    summary_lines = []
    summary_lines.append(f"🌟 *Натальная карта*")
    summary_lines.append(f"📅 {date_str}   ⏰ {time_str}   📍 {city}")
    summary_lines.append("")
    for eng in PLANETS.keys():
        deg = planet_positions.get(eng)
        sign = planet_signs.get(eng)
        sign_desc = SIGN_DESCRIPTIONS.get("Sun", {}).get(sign, "")
        ru_name = PLANET_RU.get(eng, eng)
        if deg is None:
            summary_lines.append(f"• {ru_name}: — (н/д)")
        else:
            summary_lines.append(f"• {ru_name} в *{sign}* ({deg:.1f}°) — {sign_desc}")

    summary = "\n".join(summary_lines)
    return bio, summary

# ---------------- Synastry (compatibility) ----------------
def compute_synastry_and_summary(person_a, person_b):
    """
    person_* are tuples: (name, date_str, time_str, city)
    Returns (BytesIO image, summary_text)
    """
    # compute charts for both
    bio_a, summ_a = None, None
    try:
        img_a_buf, text_a = generate_natal_chart_and_summary(person_a[1], person_a[2], person_a[3])
        img_b_buf, text_b = generate_natal_chart_and_summary(person_b[1], person_b[2], person_b[3])
    except Exception as e:
        raise ValueError(f"Ошибка при расчёте одной из карт: {e}")

    # compute inter-aspects simple: compare same planets difference
    try:
        # extract numeric positions again (could refactor to reuse)
        def get_positions_from_person(person):
            name, date_s, time_s, city = person
            # re-run safe calc to get numbers
            # parse as in generate_natal_chart_and_summary
            day = int(clean_number(date_s.split(".")[0])); month = int(clean_number(date_s.split(".")[1])); year = int(clean_number(date_s.split(".")[2]))
            hour = int(clean_number(time_s.split(":")[0])); minute = int(clean_number(time_s.split(":")[1]))
            jd = convert_local_to_jd_with_tz(date_s, time_s, city)
            if jd is None:
                decimal_hour = hour + minute / 60.0
                jd = swe.julday(year, month, day, decimal_hour)
            pos_dict = {}
            for namep, code in PLANETS.items():
                lon = safe_calc_ut(jd, code)
                pos_dict[namep] = lon
            return pos_dict

        pos_a = get_positions_from_person(person_a)
        pos_b = get_positions_from_person(person_b)

        inter_lines = []
        for eng in PLANETS.keys():
            a = pos_a.get(eng)
            b = pos_b.get(eng)
            if a is None or b is None:
                continue
            diff = abs((a - b + 180) % 360 - 180)
            # simple labels
            if diff < 8:
                mood = "Конъюнкция (сильная связь)"
            elif abs(diff - 180) < 8:
                mood = "Оппозиция (напряжение)"
            elif abs(diff - 120) < 8:
                mood = "Трин (гармония)"
            elif abs(diff - 90) < 7:
                mood = "Квадрат (конфликт)"
            elif abs(diff - 60) < 6:
                mood = "Секстиль (возможность)"
            else:
                mood = "Незначительный аспект"
            inter_lines.append(f"{PLANET_RU.get(eng,eng)}: угол ≈ {diff:.1f}° — {mood}")

        # build combined image: two mini charts side by side (simple)
        fig, axs = plt.subplots(1, 2, figsize=(12, 6), subplot_kw={'aspect':'equal'})
        # left chart
        for ax, person, pos_dict, title in [
            (axs[0], person_a, pos_a, f"{person_a[0]}"),
            (axs[1], person_b, pos_b, f"{person_b[0]}")
        ]:
            ax.set_xlim(-1.1, 1.1); ax.set_ylim(-1.1, 1.1)
            circ = plt.Circle((0,0),1, fill=False, color='lightgrey', linewidth=2)
            ax.add_artist(circ)
            # zodiac labels
            for i in range(12):
                ang = (i*30)/360*2*math.pi
                ax.text(1.08*math.cos(ang), 1.08*math.sin(ang), ZODIAC_SIGNS[i], fontsize=8, ha='center', va='center')
            for eng, lon in pos_dict.items():
                if lon is None: continue
                ang = math.radians(lon)
                x = 0.75*math.cos(ang); y = 0.75*math.sin(ang)
                ax.plot(x,y,'o', markersize=6)
                ax.text(x*1.15, y*1.15, PLANET_RU.get(eng,eng), fontsize=7, ha='center', va='center')
            ax.set_title(title)
            ax.axis('off')

        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
        buf.seek(0)
        plt.close(fig)

        summary = f"💞 Синастрия: {person_a[0]} — {person_b[0]}\n\n"
        summary += "🔗 Межпланетные аспекты (по одинаковым планетам):\n"
        summary += "\n".join(inter_lines[:40])
        summary += "\n\n(Простой анализ: конъюнкции/трины/секстили — гармония; квадраты/оппозиции — напряжение.)"
        return buf, summary

    except Exception as e:
        raise ValueError(f"Ошибка при генерации синастрии: {e}")

# ---------------- Telegram handlers ----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = [
        [InlineKeyboardButton("🔮 Натальная карта", callback_data="mode_natal")],
        [InlineKeyboardButton("💞 Синастрия", callback_data="mode_synastry")],
    ]
    await update.message.reply_text("Привет! Я AstroLuna — выбери действие:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data == "mode_natal":
        context.user_data.clear()
        context.user_data["mode"] = "natal_one"
        await query.message.reply_text("Отправь одну строку: `Имя, ДД.MM.YYYY, HH:MM, Город`", parse_mode="Markdown")
        return
    if data == "mode_synastry":
        context.user_data.clear()
        context.user_data["mode"] = "syn_a"
        await query.message.reply_text("Синастрия: отправь данные для первого человека:\n`Имя, ДД.MM.YYYY, HH:MM, Город`", parse_mode="Markdown")
        return
    if data == "menu":
        context.user_data.clear()
        await query.message.reply_text("Меню:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔮 Натальная карта", callback_data="mode_natal")],
            [InlineKeyboardButton("💞 Синастрия", callback_data="mode_synastry")]
        ]))
        return
    # repeat buttons for convenience
    if data.startswith("mode_"):
        m = data.split("_",1)[1]
        if m == "natal":
            context.user_data["mode"]="natal_one"
            await query.message.reply_text("Введи данные для натальной карты.")
        elif m == "synastry":
            context.user_data["mode"]="syn_a"
            await query.message.reply_text("Синастрия — введите первую строку.")
        return

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("mode")

    # NATAL single
    if mode == "natal_one":
        try:
            name, date_s, time_s, city = parse_input_flexible(text)
            img_buf, summary = generate_natal_chart_and_summary(date_s, time_s, city)
            # send photo then summary (split long summary)
            await update.message.reply_photo(photo=img_buf)
            # send summary in chunks if too long
            for i in range(0, len(summary), MAX_CAPTION):
                await update.message.reply_text(summary[i:i+MAX_CAPTION], parse_mode="Markdown")
            # show repeat/menu buttons
            await update.message.reply_text("Выберите:", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Сделать ещё", callback_data="mode_natal")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
            ]))
            context.user_data.clear()
            return
        except Exception as e:
            await update.message.reply_text(f"⚠️ Ошибка при расчёте карты: {e}")
            print(traceback.format_exc())
            context.user_data.clear()
            return

    # SINASTRY flow
    if mode == "syn_a":
        try:
            name, date_s, time_s, city = parse_input_flexible(text)
            context.user_data["syn_a"] = (name, date_s, time_s, city)
            context.user_data["mode"] = "syn_b"
            await update.message.reply_text("Ок. Теперь отправь данные для второго человека (в том же формате).")
            return
        except Exception as e:
            await update.message.reply_text(f"⚠️ Неверный формат: {e}")
            return

    if mode == "syn_b":
        try:
            name_b, date_b, time_b, city_b = parse_input_flexible(text)
            person_a = context.user_data.get("syn_a")
            if not person_a:
                await update.message.reply_text("⚠️ Не найдены данные первого человека. Начни заново.")
                context.user_data.clear()
                return
            person_b = (name_b, date_b, time_b, city_b)
            img_buf, summary = compute_synastry_and_summary(person_a, person_b)
            # send synastry image and summary
            await update.message.reply_photo(photo=img_buf)
            for i in range(0, len(summary), MAX_CAPTION):
                await update.message.reply_text(summary[i:i+MAX_CAPTION], parse_mode="Markdown")
            await update.message.reply_text("Выберите:", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Сделать ещё", callback_data="mode_synastry")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
            ]))
            context.user_data.clear()
            return
        except Exception as e:
            await update.message.reply_text(f"⚠️ Ошибка при расчёте синастрии: {e}")
            print(traceback.format_exc())
            context.user_data.clear()
            return

    # default fallback
    await update.message.reply_text("Нажми /start и выбери действие (Натальная карта или Синастрия).")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_router))

    print("✅ AstroLuna Advanced запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()