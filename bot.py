import asyncio
import sqlite3
import math
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = "1200659505"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}

# ===== Храним последний отправленный measurement id для каждого устройства =====
last_sent_id = {}

# ===== Telegram =====
async def send_or_update_message(text: str, uid: str):
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        if msg_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text)
                return msg_id
            except TelegramAPIError:
                print(f"⚠ Не удалось отредактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text)
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (msg.message_id, uid))
        conn.commit()
        return msg.message_id

    except Exception as e:
        print("Telegram error:", e)
        return None

# ===== Слушаем новые данные =====
async def monitor_new_measurements():
    while True:
        try:
            cursor.execute("SELECT device_uid FROM devices")
            devices = [row[0] for row in cursor.fetchall()]

            for uid in devices:
                cursor.execute("""
                    SELECT id, co2, temperature, humidity, timestamp
                    FROM measurements
                    WHERE device_uid=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (uid,))
                row = cursor.fetchone()
                if not row:
                    continue

                meas_id, co2, temp, hum, ts = row

                if last_sent_id.get(uid) == meas_id:
                    continue

                # ===== Статус кабинета =====
                status_ok = (co2 <= LIMITS["co2"] and temp >= LIMITS["temperature"] and hum >= LIMITS["humidity"])
                status_circle = "✅" if status_ok else "❌"
                status_text = "Параметры в норме" if status_ok else "Параметры вне нормы"

                # ===== Разделяем дату и время =====
                date_part, time_part = ts.split(" ")

                # ===== Формируем текст сообщения =====
                text = (
                    f"{status_circle} Состояние кабинета\n"
                    f"Дата: {date_part}\n"
                    f"Время: {time_part}\n\n"
                    f"🫁 CO₂: {co2} ppm\n"
                    f"🌡 Температура: {temp if temp is not None else 'N/A'} °C\n"
                    f"💧 Влажность: {hum if hum is not None else 'N/A'} %\n\n"
                    f"{status_text}"
                )

                msg_id = await send_or_update_message(text, uid)
                if msg_id:
                    last_sent_id[uid] = meas_id

            await asyncio.sleep(1)
        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== Запуск =====
async def main():
    try:
        await monitor_new_measurements()
    finally:
        await bot.session.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
