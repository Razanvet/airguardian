from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime, timedelta
from bot import loop  # импортируем функцию цикла из bot.py
import asyncio
@app.on_event("startup")
async def start_bot():
    asyncio.create_task(loop())


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

# ===== Модель данных =====
class IngestData(BaseModel):
    device_uid: str
    api_key: str
    co2: int
    temperature: float
    humidity: float




@app.get("/debug/measurements/all")
def debug_measurements_all():
    try:
        cursor.execute("SELECT * FROM measurements ORDER BY id ASC")
        rows = cursor.fetchall()
        # Преобразуем в список словарей для удобного просмотра
        result = [
            {
                "id": row[0],
                "device_uid": row[1],
                "co2": row[2],
                "temperature": row[3],
                "humidity": row[4],
                "timestamp": row[5]
            }
            for row in rows
        ]
        return {"rows": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e)}



# ===== Эндпоинт приёма данных =====
@app.post("/ingest")
async def ingest(data: IngestData):
    timestamp = datetime.utcnow() + timedelta(hours=3)  # МСК
    ts = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # регистрация устройства
    cursor.execute("""
        INSERT OR IGNORE INTO devices (device_uid, api_key)
        VALUES (?, ?)
    """, (data.device_uid, data.api_key))

    # сохранение измерений
    cursor.execute("""
        INSERT INTO measurements (device_uid, co2, temperature, humidity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.device_uid,
        data.co2,
        data.temperature,
        data.humidity,
        ts
    ))

    conn.commit()

    return {"status": "ok"}


