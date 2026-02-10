from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from datetime import datetime, timedelta

from bot import send_or_update_message

app = FastAPI()

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
    device_uid TEXT PRIMARY KEY,
    api_key TEXT,
    tg_message_id INTEGER
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
    "co2": {"min": 400, "max": 1000},
    "temperature": {"min": 18, "max": 27},
    "humidity": {"min": 30, "max": 70}
}

# ===== Модель =====
class IngestData(BaseModel):
    device_uid: str
    api_key: str
    co2: int
    temperature: float
    humidity: float

# ===== /ingest =====
@app.post("/ingest")
async def ingest(data: IngestData):
    ts = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    cursor.execute("""
        INSERT INTO measurements
        (device_uid, co2, temperature, humidity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (data.device_uid, data.co2, data.temperature, data.humidity, ts))
    conn.commit()

    alerts = []
    if data.co2 > LIMITS["co2"]["max"]:
        alerts.append("❗ CO₂")
    if data.temperature < LIMITS["temperature"]["min"]:
        alerts.append("❗ 🌡")
    if data.humidity < LIMITS["humidity"]["min"]:
        alerts.append("❗ 💧")

    cursor.execute(
        "SELECT tg_message_id FROM devices WHERE device_uid=?",
        (data.device_uid,)
    )
    row = cursor.fetchone()
    msg_id = row[0] if row else None

    text = (
        f"{'🚨' if alerts else '🟢'} *Состояние кабинета*\n"
        f"Кабинет: `{data.device_uid}`\n"
        f"Время: {ts}\n\n"
        f"CO₂: {data.co2} ppm\n"
        f"🌡 Температура: {data.temperature} °C\n"
        f"💧 Влажность: {data.humidity} %"
    )

    new_id = await send_or_update_message(text, msg_id)

    cursor.execute(
        "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
        (new_id, data.device_uid)
    )
    conn.commit()

    return {"status": "ok"}
