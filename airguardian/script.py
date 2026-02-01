from fastapi import FastAPI, HTTPException
import sqlite3

app = FastAPI()
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_uid TEXT UNIQUE,
  api_key TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id INTEGER,
  co2 INTEGER,
  temperature REAL,
  humidity REAL,
  pressure REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

@app.post("/ingest")
async def ingest(data: dict):

    cursor.execute(
        "SELECT id FROM devices WHERE device_uid=? AND api_key=?",
        (data["device_uid"], data["api_key"])
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(403, "Invalid device")

    cursor.execute("""
        INSERT INTO measurements
        (device_id, co2, temperature, humidity, pressure)
        VALUES (?, ?, ?, ?, ?)
    """, (
        row[0],
        data["co2"],
        data["temperature"],
        data["humidity"],
        data["pressure"]
    ))

    conn.commit()
    return {"status": "ok"}
