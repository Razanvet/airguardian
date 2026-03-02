import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command  # для /start
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher(bot)

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}
last_sent_id = {}

# ===== Кабинеты =====
SELECTED_CABINET = None
AVAILABLE_CABINETS = [f"cabinet_{i}" for i in range(101, 111)]
status_msg_id = None
notifications_enabled = True
notif_msg_id = None

# ===== Отправка или редактирование сообщения =====
async def send_or_update_message(text: str, uid: str):
    global status_msg_id
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        if msg_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text, reply_markup=buttons_kb())
                status_msg_id = msg_id
                return msg_id
            except TelegramAPIError:
                print(f"⚠ Не удалось отредактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text, reply_markup=buttons_kb())
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (msg.message_id, uid))
        conn.commit()
        status_msg_id = msg.message_id
        return msg.message_id

    except Exception as e:
        print("Telegram error:", e)
        return None

# ===== Клавиатура кнопок =====
def buttons_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            text=f"Уведомления {'✅' if notifications_enabled else '❌'}",
            callback_data="notif"
        ),
        InlineKeyboardButton(
            text="Сменить кабинет",
            callback_data="change_cabinet"
        )
    )
    return kb

# ===== Приветствие / выбор кабинета =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    global SELECTED_CABINET
    SELECTED_CABINET = None
    await send_cabinet_selection()

async def send_cabinet_selection():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=c, callback_data=c) for c in AVAILABLE_CABINETS]
    keyboard.add(*buttons)
    await bot.send_message(CHAT_ID, "Выберите кабинет для мониторинга:", reply_markup=keyboard)

# ===== Выбор кабинета =====
@dp.callback_query(lambda c: c.data in AVAILABLE_CABINETS)
async def select_cabinet(callback: types.CallbackQuery):
    global SELECTED_CABINET
    SELECTED_CABINET = callback.data
    await bot.answer_callback_query(callback.id, f"Выбран {SELECTED_CABINET}")
    await send_or_update_message("Ожидание данных...", SELECTED_CABINET)

# ===== Кнопки =====
@dp.callback_query(lambda c: c.data == "notif")
async def toggle_notifications(callback: types.CallbackQuery):
    global notifications_enabled
    notifications_enabled = not notifications_enabled
    state = "включены" if notifications_enabled else "выключены"
    await bot.answer_callback_query(callback.id, f"Уведомления {state}")
    if status_msg_id:
        await send_or_update_message("Ожидание данных...", SELECTED_CABINET)

@dp.callback_query(lambda c: c.data == "change_cabinet")
async def change_cabinet(callback: types.CallbackQuery):
    global SELECTED_CABINET, status_msg_id
    if status_msg_id:
        try:
            await bot.delete_message(chat_id=CHAT_ID, message_id=status_msg_id)
        except:
            pass
    SELECTED_CABINET = None
    status_msg_id = None
    await send_cabinet_selection()

# ===== Мониторинг новых данных =====
async def monitor_new_measurements():
    global last_sent_id, SELECTED_CABINET
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

            # ===== Уведомления каждые 2 минуты =====
            if notifications_enabled and not status_ok:
                try:
                    await send_temp_notification(uid)
                except:
                    pass

            await asyncio.sleep(1)

        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== Временное уведомление =====
async def send_temp_notification(uid):
    global notif_msg_id
    cursor.execute("""
        SELECT co2, temperature, humidity, timestamp
        FROM measurements
        WHERE device_uid=?
        ORDER BY id DESC
        LIMIT 1
    """, (uid,))
    row = cursor.fetchone()
    if not row:
        return

    co2, temp, hum, ts = row
    status_ok = (co2 <= LIMITS["co2"] and temp >= LIMITS["temperature"] and hum >= LIMITS["humidity"])
    if status_ok:
        return

    text = "⚠️ Внимание! Параметры не в норме!"
    if notif_msg_id:
        try:
            await bot.edit_message_text(chat_id=CHAT_ID, message_id=notif_msg_id, text=text)
            return
        except:
            notif_msg_id = None

    msg = await bot.send_message(CHAT_ID, text)
    notif_msg_id = msg.message_id

# ===== Запуск бота =====
async def main():
    asyncio.create_task(monitor_new_measurements())
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
