from fastapi import FastAPI, HTTPException
import sqlite3

app = FastAPI()

# ===== DATABASE =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== TABLES =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_uid TEXT UNIQUE NOT NULL,
    api_key TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    co2 INTEGER,
    temperature REAL,
    humidity REAL,
    pressure REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id)
)
""")

conn.commit()

# ===== API =====
@app.post("/ingest")
async def ingest(data: dict):

    required = ["device_uid", "api_key", "co2", "temperature", "humidity", "pressure"]
    for key in required:
        if key not in data:
            raise HTTPException(400, f"Missing {key}")

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
