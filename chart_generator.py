import os
import io
import math
from datetime import datetime
from geopy.geocoders import Nominatim
from flatlib.chart import Chart
from flatlib.datetime import Datetime
from flatlib import const
import matplotlib.pyplot as plt

def generate_natal_chart(date_str, time_str, city_name):
    """Создание натальной карты и краткого описания"""

    # Определяем координаты города
    geolocator = Nominatim(user_agent="astro_bot")
    location = geolocator.geocode(city_name)
    if not location:
        raise ValueError(f"Не удалось определить координаты для '{city_name}'")

    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    time_parts = time_str.split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1]) if len(time_parts) > 1 else 0

    # Создаём карту
    dt = Datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute, "+00:00")
    pos = (location.longitude, location.latitude)
    chart = Chart(dt, pos, hsys=const.HOUSES_PLACIDUS)

    # Рисуем круг
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect("equal")
    ax.axis("off")

    # Круг — символ зодиака
    circle = plt.Circle((0, 0), 1, color="gold", fill=False, lw=2)
    ax.add_artist(circle)

    # Разделение на 12 домов
    for i in range(12):
        angle = math.radians(i * 30)
        ax.plot([0, math.cos(angle)], [0, math.sin(angle)], color="gray", lw=1)

    # Планеты
    planets = [
        const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS,
        const.JUPITER, const.SATURN, const.URANUS, const.NEPTUNE, const.PLUTO
    ]

    for pl in planets:
        planet = chart.get(pl)
        angle = math.radians(planet.lon)
        x = 0.8 * math.cos(angle)
        y = 0.8 * math.sin(angle)
        ax.text(x, y, planet.symbol, ha="center", va="center", fontsize=14)

    # Сохраняем файл
    os.makedirs("output", exist_ok=True)
    filename = f"output/natal_chart_{date_str.replace('.', '-')}.png"
    plt.savefig(filename, bbox_inches="tight", transparent=True)
    plt.close(fig)

    # Простое описание
    sun = chart.get(const.SUN)
    moon = chart.get(const.MOON)
    asc = chart.get(const.ASC)
    summary = (
        f"🌞 Солнце в {sun.sign}\n"
        f"🌙 Луна в {moon.sign}\n"
        f"⬆️ Асцендент в {asc.sign}\n\n"
        f"✨ Это твоя натальная карта — отражение потенциала твоей души 🌌"
    )

    return filename, summary