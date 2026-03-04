from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime, timedelta
import asyncio

from bot import data_queue, main as bot_main

app = FastAPI()

conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

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
async def startup_event():
    asyncio.create_task(bot_main())

@app.get("/debug/measurements/all")
def debug_measurements():
    cursor.execute("SELECT * FROM measurements ORDER BY id ASC")
    rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "device_uid": row[1],
            "co2": row[2],
            "temperature": row[3],
            "humidity": row[4],
            "timestamp": row[5]
        })

    return {"count": len(result), "rows": result}

@app.post("/ingest")
async def ingest(data: IngestData):

    cursor.execute(
        "SELECT api_key FROM devices WHERE device_uid=?",
        (data.device_uid,)
    )
    row = cursor.fetchone()

    if row:
        if row[0] != data.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
    else:
        cursor.execute(
            "INSERT INTO devices (device_uid, api_key) VALUES (?, ?)",
            (data.device_uid, data.api_key)
        )

    timestamp = datetime.utcnow() + timedelta(hours=3)
    ts = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO measurements
        (device_uid, co2, temperature, humidity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.device_uid,
        data.co2,
        data.temperature,
        data.humidity,
        ts
    ))

    conn.commit()

    try:
        cabinet_number = int(data.device_uid.split("_")[1])

        await data_queue.put({
            "cabinet": cabinet_number,
            "co2": data.co2,
            "temperature": data.temperature,
            "humidity": data.humidity,
            "timestamp": ts
        })

    except Exception as e:
        print(f"Queue error: {e}")

    return {"status": "ok"}

