import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}
last_sent_id = {}
SELECTED_CABINET = None
AVAILABLE_CABINETS = ["cabinet_101"]
notifications_enabled = False
notification_msg_id = None

# ===== Функции =====
async def send_or_update_message(text: str, uid: str):
    global notifications_enabled
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(
                text=f"{'🔔 Выключить' if notifications_enabled else '🔔 Включить'} уведомления",
                callback_data="toggle_notifications"
            ),
            InlineKeyboardButton(
                text="🔄 Сменить кабинет",
                callback_data="change_cabinet"
            )
        )

        if msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID, message_id=msg_id, text=text, reply_markup=keyboard
                )
                return msg_id
            except Exception:
                pass

        msg = await bot.send_message(CHAT_ID, text, reply_markup=keyboard)
        cursor.execute(
            "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
            (msg.message_id, uid)
        )
        conn.commit()
        return msg.message_id
    except Exception as e:
        print("Telegram error:", e)
        return None

async def send_notification(text: str):
    global notification_msg_id
    try:
        if notification_msg_id:
            await bot.delete_message(chat_id=CHAT_ID, message_id=notification_msg_id)
        msg = await bot.send_message(CHAT_ID, text)
        notification_msg_id = msg.message_id
    except Exception as e:
        print("Notification error:", e)

# ===== Команды =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    global SELECTED_CABINET
    SELECTED_CABINET = None

    keyboard = InlineKeyboardMarkup(row_width=1)
    for cabinet in AVAILABLE_CABINETS:
        keyboard.add(
            InlineKeyboardButton(text=cabinet, callback_data=cabinet)
        )

    await message.answer(
        "Привет! Выберите кабинет для мониторинга:",
        reply_markup=keyboard
    )

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    global SELECTED_CABINET, notifications_enabled

    if callback.data in AVAILABLE_CABINETS:
        SELECTED_CABINET = callback.data
        await bot.answer_callback_query(callback.id, text=f"Выбран {SELECTED_CABINET}")
        await send_or_update_message("Ожидание данных...", SELECTED_CABINET)

    elif callback.data == "toggle_notifications":
        notifications_enabled = not notifications_enabled
        await bot.answer_callback_query(
            callback.id,
            text=f"{'Уведомления включены' if notifications_enabled else 'Уведомления выключены'}"
        )
        if SELECTED_CABINET:
            await send_or_update_message("Обновление состояния кабинета...", SELECTED_CABINET)

    elif callback.data == "change_cabinet":
        SELECTED_CABINET = None
        await bot.answer_callback_query(callback.id, text="Выберите кабинет заново")
        if callback.message:
            try:
                await bot.delete_message(chat_id=CHAT_ID, message_id=callback.message.message_id)
            except Exception:
                pass
        await start_command(await bot.get_chat(CHAT_ID))

# ===== Мониторинг данных =====
async def monitor_new_measurements():
    global SELECTED_CABINET
    while True:
        try:
            if not SELECTED_CABINET:
                await asyncio.sleep(1)
                continue

            uid = SELECTED_CABINET
            cursor.execute("""
                SELECT id, co2, temperature, humidity, timestamp
                FROM measurements
                WHERE device_uid=?
                ORDER BY id DESC
                LIMIT 1
            """, (uid,))
            row = cursor.fetchone()
            if not row:
                await asyncio.sleep(1)
                continue

            meas_id, co2, temp, hum, ts = row
            if last_sent_id.get(uid) == meas_id:
                await asyncio.sleep(1)
                continue

            status_ok = (co2 <= LIMITS["co2"] and temp >= LIMITS["temperature"] and hum >= LIMITS["humidity"])
            status_circle = "✅" if status_ok else "❌"
            status_text = "Параметры в норме" if status_ok else "Параметры вне нормы"

            date_part, time_part = ts.split(" ")
            text = (
                f"{status_circle} Состояние кабинета\n"
                f"Дата: {date_part}\n"
                f"Время: {time_part}\n\n"
                f"🫁 CO₂: {co2} ppm\n"
                f"🌡 Температура: {temp if temp is not None else 'N/A'} °C\n"
                f"💧 Влажность: {hum if hum is not None else 'N/A'} %\n\n"
                f"{status_text}"
            )

            await send_or_update_message(text, uid)

            if notifications_enabled and not status_ok:
                await send_notification("⚠️ Внимание! Параметры не в норме!")

            last_sent_id[uid] = meas_id
            await asyncio.sleep(1)

        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== Запуск =====
async def main():
    asyncio.create_task(monitor_new_measurements())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
