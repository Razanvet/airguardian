import asyncio
import sqlite3
from aiogram import Bot, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Dispatcher

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505  # Твой чат ID

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# В 3.x просто создаём Dispatcher без передачи bot
dp = Dispatcher()

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}

# ===== Храним последний отправленный measurement id для каждого устройства =====
last_sent_id = {}

# ===== Выбор кабинета =====
SELECTED_CABINET = None
AVAILABLE_CABINETS = [f"cabinet_{i}" for i in range(101, 111)]


# ===== Отправка или редактирование сообщения =====
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


# ===== Приветствие и выбор кабинета =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    global SELECTED_CABINET
    SELECTED_CABINET = None

    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cabinet in AVAILABLE_CABINETS:
        buttons.append(
            InlineKeyboardButton(
                text=cabinet if cabinet == "cabinet_101" else f"{cabinet} ❌",
                callback_data=cabinet
            )
        )
    keyboard.add(*buttons)

    await message.answer(
        "Привет! 👋 Выберите кабинет для мониторинга (пока работает только cabinet_101):",
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data in AVAILABLE_CABINETS)
async def select_cabinet(callback_query: types.CallbackQuery):
    global SELECTED_CABINET
    if callback_query.data == "cabinet_101":
        SELECTED_CABINET = callback_query.data
        await callback_query.answer(text=f"Выбран {SELECTED_CABINET}")
        await bot.send_message(callback_query.from_user.id, "✅ Кабинет выбран! Данные будут отображаться здесь.")
    else:
        await callback_query.answer(text="⚠️ Этот кабинет пока не работает", show_alert=True)


# ===== Слушаем новые данные =====
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
            last_sent_id[uid] = meas_id

            await asyncio.sleep(1)

        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)


# ===== Запуск бота =====
async def main():
    try:
        asyncio.create_task(monitor_new_measurements())
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
