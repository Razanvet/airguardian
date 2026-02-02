from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from datetime import datetime

app = FastAPI()

# ===== БАЗА ДАННЫХ =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== ТАБЛИЦЫ =====
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
    pressure REAL,
    timestamp TEXT
)
""")

conn.commit()

# ===== МОДЕЛЬ ДАННЫХ =====
class IngestData(BaseModel):
    device_uid: str
    api_key: str
    co2: int
    temperature: float
    humidity: float
    pressure: float

# ===== INGEST ENDPOINT =====
@app.post("/ingest")
async def ingest(data: IngestData):

    # 🔹 АВТО-РЕГИСТРАЦИЯ УСТРОЙСТВА
    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    # 🔹 СОХРАНЕНИЕ ИЗМЕРЕНИЙ
    cursor.execute("""
        INSERT INTO measurements
        (device_uid, co2, temperature, humidity, pressure, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data.device_uid,
        data.co2,
        data.temperature,
        data.humidity,
        data.pressure,
        datetime.utcnow().isoformat()
    ))

    conn.commit()

    return {
        "status": "ok",
        "device_uid": data.device_uid
    }

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
            "pressure": r[3],
            "timestamp": r[5]
        }
        for r in rows
    ]
