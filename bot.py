import sqlite3
import asyncio
import requests
import math
from datetime import datetime
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

# ===== Настройки бота =====
TELEGRAM_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = "1200659505"

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Пороговые значения =====
LIMITS = {
    "co2": {"min": 400, "max": 1200},
    "temperature": {"min": 18, "max": 27},
    "humidity": {"min": 30, "max": 70}
}

# ===== Параметры пространства =====
CLASS_VOLUME = 8 * 6 * 3      # объем помещения (м³)
NUM_WINDOWS = 4
WINDOW_WIDTH = 1.5
WINDOW_OPEN = 0.08
C_D = 0.6
CO2_GEN = 0.005               # м³/ч на человека
OUTSIDE_CO2 = 400
MAX_CO2 = 1000
NUM_PEOPLE = 20

# ===== Функция отправки/обновления сообщений =====
async def send_or_update_message(text: str, message_id: int | None = None) -> int:
    try:
        if message_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=message_id, text=text)
                return message_id
            except TelegramAPIError:
                msg = await bot.send_message(chat_id=CHAT_ID, text=text)
                return msg.message_id
        else:
            msg = await bot.send_message(chat_id=CHAT_ID, text=text)
            return msg.message_id
    except Exception as e:
        print("Telegram send error:", e)
        return message_id or 0

# ===== Получаем погоду (температура и ветер) =====
def get_weather():
    YANDEX_KEY = "<YOUR_YANDEX_WEATHER_KEY>"  # вставь свой ключ
    lat, lon = 59.12, 51.93  # Координаты Кирово‑Чепецка
    try:
        url = "https://api.weather.yandex.ru/v2/forecast"
        params = {"lat": lat, "lon": lon, "extra": "true"}
        headers = {"X-Yandex-Weather-Key": YANDEX_KEY}
        resp = requests.get(url, headers=headers, params=params, timeout=5).json()
        fact = resp.get("fact", {})
        temp_out = fact.get("temp", 0)
        wind_speed = fact.get("wind_speed", 0)  # скорость ветра, м/с :contentReference[oaicite:1]{index=1}
        return {"temp": temp_out, "wind": wind_speed}
    except Exception as e:
        print("Error getting weather:", e)
        return {"temp": 0, "wind": 0}

# ===== Расчёт времени микропроветривания =====
def calculate_ventilation(temp_in, temp_out, wind_speed):
    delta_T = temp_in - temp_out
    A_open = WINDOW_WIDTH * WINDOW_OPEN
    g = 9.81

    # поток воздуха учитывая разность температур и ветер
    Q_per = C_D * A_open * math.sqrt(2 * g * delta_T / (temp_in + 273.15) + wind_speed**2)
    Q_all = Q_per * NUM_WINDOWS

    # необходимый поток для CO2
    G = NUM_PEOPLE * CO2_GEN
    Q_needed = G / ((MAX_CO2 - OUTSIDE_CO2) * 1e-6)

    time_h = CLASS_VOLUME / max(Q_all, 1)  # ч
    time_min = time_h * 60
    return round(time_min)

# ===== Проверка устройств =====
async def check_all_devices():
    cursor.execute("SELECT device_uid, tg_message_id FROM devices")
    devices = cursor.fetchall()

    for device_uid, message_id in devices:
        cursor.execute("""
            SELECT co2, temperature, humidity, timestamp
            FROM measurements
            WHERE device_uid=?
            ORDER BY id DESC
            LIMIT 1
        """, (device_uid,))
        row = cursor.fetchone()
        if not row:
            continue

        co2, temp, hum, ts = row
        weather = get_weather()
        temp_out = weather["temp"]
        wind_speed = weather["wind"]

        vent_time = calculate_ventilation(temp, temp_out, wind_speed)

        alerts = []
        if co2 < LIMITS["co2"]["min"] or co2 > LIMITS["co2"]["max"]:
            alerts.append(f"❗ CO₂: {co2} ppm")
        if temp < LIMITS["temperature"]["min"] or temp > LIMITS["temperature"]["max"]:
            alerts.append(f"❗ 🌡 Температура: {temp:.1f} °C")
        if hum < LIMITS["humidity"]["min"] or hum > LIMITS["humidity"]["max"]:
            alerts.append(f"❗ 💧 Влажность: {hum:.1f} %")

        status_icon = "🚨" if alerts else "🟢"
        text = (
            f"{status_icon} *Состояние кабинета*\n"
            f"Кабинет: `{device_uid}`\n"
            f"Время: {ts}\n\n"
            f"*Данные:*\n"
            f"CO₂: {co2} ppm\n"
            f"Температура: {temp:.1f} °C\n"
            f"Влажность: {hum:.1f} %\n\n"
            f"🌦️ Температура на улице: {temp_out} °C\n"
            f"💨 Скорость ветра: {wind_speed} м/с\n"
            f"⏱ Время проветривания: ~{vent_time} мин\n"
        )

        if alerts:
            text += "\n⚠ Отклонения:\n" + "\n".join(alerts)

        new_message_id = await send_or_update_message(text, message_id)
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (new_message_id, device_uid))
        conn.commit()

# ===== Главный цикл =====
async def main_loop():
    while True:
        await check_all_devices()
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_loop())
