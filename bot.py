import asyncio
import sqlite3
from aiogram import Bot, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}

# ===== Храним последнее сообщение и последние данные =====
last_sent_id = {}
last_data = {}

# ===== Кабинеты =====
SELECTED_CABINET = None
AVAILABLE_CABINETS = [f"cabinet_{i}" for i in range(101, 111)]

# ===== Статус уведомлений =====
notifications_enabled = {}

# ===== Функции =====
async def send_or_update_message(uid: str, text: str):
    """Редактирует существующее сообщение с данными или создаёт новое."""
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        if msg_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text,
                                            reply_markup=build_buttons(uid))
                return msg_id
            except TelegramAPIError:
                print(f"⚠ Не удалось отредактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text, reply_markup=build_buttons(uid))
        cursor.execute("INSERT OR IGNORE INTO devices (device_uid, api_key, tg_message_id) VALUES (?, ?, ?)",
                       (uid, "", msg.message_id))
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (msg.message_id, uid))
        conn.commit()
        return msg.message_id

    except Exception as e:
        print("Telegram error:", e)
        return None

def build_buttons(uid: str):
    keyboard = InlineKeyboardMarkup(row_width=1)
    notif_status = "Выключить уведомления" if notifications_enabled.get(uid, False) else "Включить уведомления"
    keyboard.add(
        InlineKeyboardButton(text=notif_status, callback_data=f"notif:{uid}"),
        InlineKeyboardButton(text="Сменить кабинет", callback_data=f"switch:{uid}")
    )
    return keyboard

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

            last_sent_id[uid] = meas_id
            last_data[uid] = {"co2": co2, "temperature": temp, "humidity": hum, "timestamp": ts}

            status_ok = (co2 <= LIMITS["co2"] and temp >= LIMITS["temperature"] and hum >= LIMITS["humidity"])
            status_circle = "✅" if status_ok else "❌"
            status_text = "Параметры в норме" if status_ok else "Параметры вне нормы"
            date_part, time_part = ts.split(" ")

            text = (
                f"{status_circle} Состояние кабинета\n"
                f"Дата: {date_part}\n"
                f"Время: {time_part}\n\n"
                f"🫁 CO₂: {co2} ppm\n"
                f"🌡 Температура: {temp} °C\n"
                f"💧 Влажность: {hum} %\n\n"
                f"{status_text}"
            )

            await send_or_update_message(uid, text)

            # ===== Уведомления =====
            if not status_ok and notifications_enabled.get(uid, False):
                asyncio.create_task(send_alert(uid))

            await asyncio.sleep(1)
        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

async def send_alert(uid: str):
    """Отправка уведомления каждые 2 минуты, перезаписывая предыдущее."""
    text = "⚠️ Внимание! Параметры не в норме!"
    cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
    row = cursor.fetchone()
    msg_id = row[0] if row else None

    for _ in range(3):  # три цикла уведомления с интервалом 2 минуты (можно увеличить)
        try:
            if msg_id:
                try:
                    await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text)
                except TelegramAPIError:
                    msg = await bot.send_message(CHAT_ID, text)
                    msg_id = msg.message_id
            else:
                msg = await bot.send_message(CHAT_ID, text)
                msg_id = msg.message_id
        except Exception as e:
            print("Alert error:", e)
        await asyncio.sleep(120)

# ===== Callback обработчики =====
@bot.message()
async def dummy_handler(message: types.Message):
    await message.reply("Используйте /start")

@bot.callback_query_handler(lambda c: c.data.startswith("notif:"))
async def toggle_notifications(callback_query: types.CallbackQuery):
    uid = callback_query.data.split(":")[1]
    notifications_enabled[uid] = not notifications_enabled.get(uid, False)
    await bot.answer_callback_query(callback_query.id, text="Статус уведомлений изменён")
    # Обновляем кнопки
    await send_or_update_message(uid, "Обновление статуса…")

@bot.callback_query_handler(lambda c: c.data.startswith("switch:"))
async def switch_cabinet(callback_query: types.CallbackQuery):
    uid = callback_query.data.split(":")[1]
    global SELECTED_CABINET
    SELECTED_CABINET = None
    await bot.delete_message(chat_id=CHAT_ID, message_id=last_sent_id.get(uid, 0))
    await show_cabinet_selection(callback_query.from_user.id)

async def show_cabinet_selection(user_id: int):
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cabinet in AVAILABLE_CABINETS:
        buttons.append(InlineKeyboardButton(text=cabinet, callback_data=cabinet))
    keyboard.add(*buttons)
    await bot.send_message(user_id, "Выберите кабинет для мониторинга:", reply_markup=keyboard)

@bot.callback_query_handler(lambda c: c.data in AVAILABLE_CABINETS)
async def select_cabinet(callback_query: types.CallbackQuery):
    global SELECTED_CABINET
    SELECTED_CABINET = callback_query.data
    uid = SELECTED_CABINET

    # Сообщение ожидания данных
    text = (
        "Ожидание данных…\n"
        "CO₂: –\n"
        "Температура: –\n"
        "Влажность: –"
    )
    msg = await bot.send_message(callback_query.from_user.id, text, reply_markup=build_buttons(uid))

    # Сохраняем message_id в БД
    cursor.execute(
        "INSERT OR IGNORE INTO devices (device_uid, api_key, tg_message_id) VALUES (?, ?, ?)",
        (uid, "", msg.message_id)
    )
    cursor.execute(
        "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
        (msg.message_id, uid)
    )
    conn.commit()
    await bot.answer_callback_query(callback_query.id, text=f"Выбран {SELECTED_CABINET}")

# ===== Запуск =====
async def main():
    asyncio.create_task(monitor_new_measurements())
    await bot.start_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
