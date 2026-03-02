import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command, Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}

# ===== Состояние =====
last_sent_id = {}
SELECTED_CABINET = None
AVAILABLE_CABINETS = ["cabinet_101"]
notifications_enabled = True
status_msg_id = None
alert_msg_id = None

# ===== Отправка или редактирование состояния кабинета =====
async def send_or_update_message(text: str, uid: str):
    global status_msg_id
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        # Inline кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔔 Уведомления", callback_data="notif")],
            [InlineKeyboardButton("🔄 Сменить кабинет", callback_data="change_cabinet")]
        ])

        if msg_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text, reply_markup=keyboard)
                status_msg_id = msg_id
                return msg_id
            except:
                print(f"⚠ Не удалось отредактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text, reply_markup=keyboard)
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (msg.message_id, uid))
        conn.commit()
        status_msg_id = msg.message_id
        return msg.message_id
    except Exception as e:
        print("Telegram error:", e)
        return None

# ===== Callback обработчики =====
@dp.callback_query(Text("notif"))
async def toggle_notifications(callback: types.CallbackQuery):
    global notifications_enabled
    notifications_enabled = not notifications_enabled
    state = "включены" if notifications_enabled else "выключены"
    await bot.answer_callback_query(callback.id, f"Уведомления {state}")

@dp.callback_query(Text("change_cabinet"))
async def change_cabinet(callback: types.CallbackQuery):
    global SELECTED_CABINET, status_msg_id
    await bot.delete_message(chat_id=CHAT_ID, message_id=status_msg_id)
    SELECTED_CABINET = None
    status_msg_id = None
    await send_cabinet_selection()

# ===== Выбор кабинета =====
async def send_cabinet_selection():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(c, callback_data=c) for c in AVAILABLE_CABINETS]
    keyboard.add(*buttons)
    await bot.send_message(CHAT_ID, "Выберите кабинет:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data in AVAILABLE_CABINETS)
async def select_cabinet(callback: types.CallbackQuery):
    global SELECTED_CABINET
    SELECTED_CABINET = callback.data
    await bot.answer_callback_query(callback.id, f"Выбран {SELECTED_CABINET}")
    await send_or_update_message("Ожидание данных...", SELECTED_CABINET)

# ===== Мониторинг новых измерений =====
async def monitor_new_measurements():
    global alert_msg_id
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
                f"🫁 CO₂: {co2}\n"
                f"🌡 Температура: {temp}\n"
                f"💧 Влажность: {hum}\n\n"
                f"{status_text}"
            )

            await send_or_update_message(text, uid)
            last_sent_id[uid] = meas_id

            # ===== Уведомления =====
            if notifications_enabled and not status_ok:
                if alert_msg_id:
                    try:
                        await bot.delete_message(CHAT_ID, alert_msg_id)
                    except:
                        pass
                alert_msg_id = await bot.send_message(CHAT_ID, "⚠️ Внимание! Параметры не в норме!")

            await asyncio.sleep(2)  # проверка каждые 2 секунды
        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== Запуск бота =====
async def main():
    asyncio.create_task(monitor_new_measurements())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
