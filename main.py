import math
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime, timedelta

from bot import send_or_update_message  # ваш Telegram bot

app = FastAPI()

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Таблицы =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
    device_uid TEXT PRIMARY KEY,
    api_key TEXT,
    tg_message_id INTEGER,
    L REAL,
    W REAL,
    H REAL,
    N INTEGER,
    num_windows INTEGER,
    W_win REAL,
    H_win REAL,
    h_open REAL,
    lat REAL,
    lon REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_uid TEXT,
    co2 INTEGER,
    temperature REAL,
    humidity REAL,
    timestamp TEXT
)
""")
conn.commit()

# ===== Пороговые значения =====
LIMITS = {
    "co2": {"min": 400, "max": 1200},
    "temperature": {"min": 18, "max": 27},
    "humidity": {"min": 30, "max": 70}
}

# ===== Yandex Weather API =====
YANDEX_KEY = "<YOUR_YANDEX_WEATHER_KEY>"
YANDEX_URL = "https://api.weather.yandex.ru/graphql/query"

def get_weather(lat: float, lon: float):
    headers = {
        "X-Yandex-Weather-Key": YANDEX_KEY,
        "Content-Type": "application/json"
    }
    query = f'''
    {{
      weatherByPoint(request: {{lat: {lat}, lon: {lon}}}) {{
        now {{
          temperature
          windSpeed
        }}
      }}
    }}
    '''
    try:
        res = requests.post(YANDEX_URL, headers=headers, json={"query": query}, timeout=10)
        data = res.json()
        now = data.get("data", {}).get("weatherByPoint", {}).get("now", {})
        return {
            "temperature": now.get("temperature", 0),
            "wind_speed": now.get("windSpeed", 0)
        }
    except Exception as e:
        print("Weather API error:", e)
        # Возвращаем стандартные значения если ошибка
        return {"temperature": 0, "wind_speed": 0}

# ===== Модель данных =====
class IngestData(BaseModel):
    device_uid: str
    api_key: str
    co2: int
    temperature: float
    humidity: float

# ===== Эндпоинт /ingest =====
@app.post("/ingest")
async def ingest(data: IngestData):
    timestamp = datetime.utcnow() + timedelta(hours=3)  # МСК
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # --- регистрация устройства ---
    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    # --- сохранение измерений ---
    cursor.execute("""
        INSERT INTO measurements (device_uid, co2, temperature, humidity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.device_uid,
        data.co2,
        data.temperature,
        data.humidity,
        ts_str
    ))
    conn.commit()

    # --- проверка порогов ---
    alerts = []

    if data.co2 < LIMITS["co2"]["min"] or data.co2 > LIMITS["co2"]["max"]:
        alerts.append("❗ CO₂: {} ppm".format(data.co2))

    if data.temperature < LIMITS["temperature"]["min"] or data.temperature > LIMITS["temperature"]["max"]:
        alerts.append("❗ 🌡 Температура: {:.1f} °C".format(data.temperature))

    if data.humidity < LIMITS["humidity"]["min"] or data.humidity > LIMITS["humidity"]["max"]:
        alerts.append("❗ 💧 Влажность: {:.1f} %".format(data.humidity))

    status_icon = "🚨" if alerts else "🟢"

    text = (
        f"{status_icon} *Состояние кабинета*\n"
        f"Кабинет: `{data.device_uid}`\n"
        f"Время: {ts_str}\n\n"
        f"*Данные:*\n"
        f"CO₂: {data.co2} ppm\n"
        f"Температура: {data.temperature} °C\n"
        f"Влажность: {data.humidity} %\n"
    )

    if alerts:
        text += "\n⚠ Отклонения:\n" + "\n".join(alerts)

    # --- получаем message_id ---
    cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (data.device_uid,))
    row = cursor.fetchone()
    message_id = row[0] if row else None

    # --- отправка / обновление ---
    new_message_id = await send_or_update_message(text, message_id)

    # --- сохраняем message_id ---
    cursor.execute("""
        UPDATE devices SET tg_message_id=?
        WHERE device_uid=?
    """, (new_message_id, data.device_uid))
    conn.commit()

    return {"status": "ok"}


# ===== Эндпоинт /ventilation =====
@app.get("/ventilation/{device_uid}")
def ventilation(device_uid: str):
    cursor.execute("""
        SELECT L, W, H, N, num_windows, W_win, H_win, h_open, lat, lon
        FROM devices
        WHERE device_uid=?
    """, (device_uid,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    L, W, H, N, num_windows, W_win, H_win, h_open, lat, lon = row

    weather = get_weather(lat, lon)
    T_out = weather["temperature"]
    v_wind = weather["wind_speed"]

    # === расчёт по твоему скрипту ===
    V = L * W * H
    G = N * 0.005
    C_max, C_out = 1000, 400
    Q_CO2 = G / ((C_max - C_out) * 1e-6)

    A_open = W_win * h_open
    T_avg = (20 + T_out)/2 + 273.15
    delta_T = 20 - T_out
    g = 9.81

    Q_per_window = 0.6 * A_open * math.sqrt(2 * g * H_win * (delta_T / T_avg) + v_wind**2)
    Q_window = Q_per_window * num_windows

    t_h = V / Q_window if Q_window > 0 else float("inf")
    t_min = t_h * 60

    return {
        "room_volume": V,
        "needed_flow": Q_CO2,
        "actual_flow": Q_window,
        "ventilation_time_min": round(t_min),
        "weather_out": weather
    }
