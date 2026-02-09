from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from datetime import datetime

from bot import send_or_update_message  # импорт бота

app = FastAPI()

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Таблицы =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
    device_uid TEXT PRIMARY KEY,
    api_key TEXT,
    tg_message_id INTEGER
);


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

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # --- регистрация устройства ---
    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    # --- сохранение измерений ---
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

    # --- проверка порогов ---
    alerts = []

    if data.co2 < LIMITS["co2"]["min"] or data.co2 > LIMITS["co2"]["max"]:
        alerts.append(f"CO₂: {data.co2} ppm")

    if data.temperature < LIMITS["temperature"]["min"] or data.temperature > LIMITS["temperature"]["max"]:
        alerts.append(f"🌡 Температура: {data.temperature} °C")

    if data.humidity < LIMITS["humidity"]["min"] or data.humidity > LIMITS["humidity"]["max"]:
        alerts.append(f"💧 Влажность: {data.humidity} %")

    status_icon = "🚨" if alerts else "🟢"

    text = (
        f"{status_icon} *Состояние кабинета*\n"
        f"Кабинет: `{data.device_uid}`\n"
        f"Время: {timestamp}\n\n"
        f"*Данные:*\n"
        f"CO₂: {data.co2} ppm\n"
        f"Температура: {data.temperature} °C\n"
        f"Влажность: {data.humidity} %\n"
    )

    if alerts:
        text += "\n⚠ *Отклонения:*\n" + "\n".join(alerts)

    # --- получаем message_id ---
    cursor.execute(
        "SELECT tg_message_id FROM devices WHERE device_uid=?",
        (data.device_uid,)
    )
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


