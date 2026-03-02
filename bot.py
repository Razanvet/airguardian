import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== ТВОИ ДАННЫЕ =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== НАСТРОЙКИ =====
LIMITS = {
    "co2": 1000,
    "temperature": 18,
    "humidity": 30
}

AVAILABLE_CABINETS = [f"cabinet_{i}" for i in range(101, 111)]
SELECTED_CABINET = None
NOTIFICATIONS_ENABLED = True
last_measurement_id = {}
last_alert_time = {}


# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    global SELECTED_CABINET
    SELECTED_CABINET = None

    buttons = [
        InlineKeyboardButton(
            text=cab if cab == "cabinet_101" else f"{cab} ❌",
            callback_data=cab
        )
        for cab in AVAILABLE_CABINETS
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+2] for i in range(0, len(buttons), 2)])

    await message.answer(
        "Выберите кабинет (работает только cabinet_101):",
        reply_markup=keyboard
    )


# ===== ВЫБОР КАБИНЕТА =====
@dp.callback_query(F.data.in_(AVAILABLE_CABINETS))
async def cabinet_selected(callback: types.CallbackQuery):
    global SELECTED_CABINET

    if callback.data == "cabinet_101":
        SELECTED_CABINET = callback.data
        await callback.answer("Кабинет выбран")
        await bot.send_message(CHAT_ID, "✅ Мониторинг запущен")
    else:
        await callback.answer("Этот кабинет пока недоступен", show_alert=True)


# ===== ОБНОВЛЕНИЕ / ОТПРАВКА СООБЩЕНИЯ =====
async def send_or_update(uid, text):
    cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
    row = cursor.fetchone()

    if row and row[0]:
        try:
            await bot.edit_message_text(text, CHAT_ID, row[0])
            return
        except:
            pass

    msg = await bot.send_message(CHAT_ID, text)
    cursor.execute(
        "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
        (msg.message_id, uid)
    )
    conn.commit()


# ===== МОНИТОРИНГ =====
async def monitor():
    global SELECTED_CABINET

    while True:
        if not SELECTED_CABINET:
            await asyncio.sleep(2)
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
            await asyncio.sleep(5)
            continue

        meas_id, co2, temp, hum, ts = row

        if last_measurement_id.get(uid) == meas_id:
            await asyncio.sleep(5)
            continue

        status_ok = (
            co2 <= LIMITS["co2"] and
            temp >= LIMITS["temperature"] and
            hum >= LIMITS["humidity"]
        )

        circle = "🟢" if status_ok else "🔴"
        status_text = "Параметры в норме" if status_ok else "Параметры вне нормы"

        date_part, time_part = ts.split(" ")

        text = (
            f"{circle} Состояние кабинета\n\n"
            f"Дата: {date_part}\n"
            f"Время: {time_part}\n\n"
            f"🫁 CO₂: {co2} ppm\n"
            f"🌡 Температура: {temp} °C\n"
            f"💧 Влажность: {hum} %\n\n"
            f"{status_text}"
        )

        await send_or_update(uid, text)
        last_measurement_id[uid] = meas_id

        # ===== УВЕДОМЛЕНИЯ КАЖДЫЕ 2 МИН =====
        if not status_ok and NOTIFICATIONS_ENABLED:
            now = asyncio.get_event_loop().time()
            if uid not in last_alert_time or now - last_alert_time[uid] > 120:
                await bot.send_message(CHAT_ID, "⚠️ Внимание! Параметры вне нормы!")
                last_alert_time[uid] = now

        await asyncio.sleep(10)


# ===== ГЛАВНАЯ ФУНКЦИЯ =====
async def main():
    asyncio.create_task(monitor())
    await dp.start_polling(bot)
