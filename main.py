from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bot import dp, bot, main as bot_main, data_queue
import sqlite3
from datetime import datetime, timedelta
import asyncio

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

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_measurements_device
ON measurements(device_uid)
""")

conn.commit()

class IngestData(BaseModel):
    device_uid: str
    api_key: str
    co2: int
    temperature: float
    humidity: float

@app.on_event("startup")
async def start_bot():
    asyncio.create_task(bot_main())

@app.post("/ingest")
async def ingest(data: IngestData):
    # Проверка устройства
    cursor.execute("SELECT api_key FROM devices WHERE device_uid=?", (data.device_uid,))
    row = cursor.fetchone()
    if row:
        if row[0] != data.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
    else:
        cursor.execute("INSERT INTO devices (device_uid, api_key) VALUES (?, ?)", (data.device_uid, data.api_key))

    # Время (МСК)
    ts = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "INSERT INTO measurements (device_uid, co2, temperature, humidity, timestamp) VALUES (?, ?, ?, ?, ?)",
        (data.device_uid, data.co2, data.temperature, data.humidity, ts)
    )
    conn.commit()

    # ===== Отправляем данные в очередь бота =====
    cabinet_number = 101  # <-- тут нужно сопоставление device_uid -> кабинет
    await data_queue.put({
        "cabinet": cabinet_number,
        "co2": data.co2,
        "temperature": data.temperature,
        "humidity": data.humidity
    })

    return {"status": "ok"}
