from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from datetime import datetime

from bot import send_alert  # импорт бота

app = FastAPI()

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Таблицы =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
    device_uid TEXT PRIMARY KEY,
    api_key TEXT
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

    # 🔹 Авто-регистрация устройства
    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    # 🔹 Сохранение измерений
    timestamp = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO measurements
        (device_uid, co2, temperature, humidity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.device_uid,
        data.co2,
        data.temperature,
        data.humidity,
        timestamp
    ))
    conn.commit()

    # 🔹 Проверка порогов
    alerts = []

    # --- CO2 ---
    if data.co2 < LIMITS["co2"]["min"]:
        alerts.append(f"🔻 CO₂ слишком низкий: {data.co2} ppm")
    elif data.co2 > LIMITS["co2"]["max"]:
        alerts.append(f"🔺 CO₂ слишком высокий: {data.co2} ppm")

    # --- Temperature ---
    if data.temperature < LIMITS["temperature"]["min"]:
        alerts.append(f"❄ Температура слишком низкая: {data.temperature} °C")
    elif data.temperature > LIMITS["temperature"]["max"]:
        alerts.append(f"🔥 Температура слишком высокая: {data.temperature} °C")

    # --- Humidity ---
    if data.humidity < LIMITS["humidity"]["min"]:
        alerts.append(f"🌵 Влажность слишком низкая: {data.humidity} %")
    elif data.humidity > LIMITS["humidity"]["max"]:
        alerts.append(f"💧 Влажность слишком высокая: {data.humidity} %")

    # 🔹 Отправка в Telegram (async/await)
    if alerts:
        message = (
            f"🚨 *ОТКЛОНЕНИЕ ОТ НОРМЫ*\n"
            f"Кабинет: {data.device_uid}\n"
            f"Время измерения (UTC): {timestamp}\n\n"
            + "\n".join(alerts)
        )
        await send_alert(message)  # await гарантирует выполнение

    return {"status": "ok", "device_uid": data.device_uid, "timestamp": timestamp}


@app.get("/data")
def get_data(limit: int = 20):
    cursor.execute("""
        SELECT device_uid, co2, temperature, humidity, pressure, timestamp
        FROM measurements
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    return [
        {
            "device_uid": r[0],
            "co2": r[1],
            "temperature": r[2],
            "humidity": r[3],
            "timestamp": r[5]
        }
        for r in rows
    ]

