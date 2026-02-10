import sqlite3
import asyncio
from aiogram import Bot, types
from aiogram.exceptions import TelegramAPIError



# ===== Настройки бота =====
TELEGRAM_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"

bot = Bot(token=TELEGRAM_TOKEN, parse_mode="Markdown")

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Пороговые значения =====
LIMITS = {
    "co2": {"min": 400, "max": 1200},
    "temperature": {"min": 18, "max": 27},
    "humidity": {"min": 30, "max": 70}
}

async def send_or_update_message(text: str, message_id: int | None = None) -> int:
    chat_id = "1200659505" 
    try:
        if message_id:
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
                return message_id
            except TelegramAPIError:
                msg = await bot.send_message(chat_id=chat_id, text=text)
                return msg.message_id
        else:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            return msg.message_id
    except Exception as e:
        print("Telegram send error:", e)
        return message_id or 0
async def check_all_devices():
    cursor.execute("SELECT device_uid, tg_message_id FROM devices")
    devices = cursor.fetchall()

    for device_uid, message_id in devices:
        cursor.execute("""
            SELECT co2, temperature, humidity, timestamp
            FROM measurements
            WHERE device_uid=?
            ORDER BY id DESC
            LIMIT 1
        """, (device_uid,))
        row = cursor.fetchone()
        if not row:
            continue

        co2, temp, hum, ts = row
        alerts = []

        if co2 < LIMITS["co2"]["min"] or co2 > LIMITS["co2"]["max"]:
            alerts.append(f"❗ CO₂: {co2} ppm")
        if temp < LIMITS["temperature"]["min"] or temp > LIMITS["temperature"]["max"]:
            alerts.append(f"❗ 🌡 Температура: {temp:.1f} °C")
        if hum < LIMITS["humidity"]["min"] or hum > LIMITS["humidity"]["max"]:
            alerts.append(f"❗ 💧 Влажность: {hum:.1f} %")

        status_icon = "🚨" if alerts else "🟢"
        text = (
            f"{status_icon} *Состояние кабинета*\n"
            f"Кабинет: `{device_uid}`\n"
            f"Время: {ts}\n\n"
            f"*Данные:*\n"
            f"CO₂: {co2} ppm\n"
            f"Температура: {temp:.1f} °C\n"
            f"Влажность: {hum:.1f} %\n"
        )

        if alerts:
            text += "\n⚠ Отклонения:\n" + "\n".join(alerts)

        # Отправка или обновление
        new_message_id = await send_or_update_message(text, message_id)

        # Сохраняем message_id в БД
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (new_message_id, device_uid))
        conn.commit()

async def main_loop():
    while True:
        await check_all_devices()
        await asyncio.sleep(60)  # проверка каждые 60 секунд

if __name__ == "__main__":
    asyncio.run(main_loop())



