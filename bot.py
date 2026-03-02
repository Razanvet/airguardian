import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== ДАННЫЕ =====
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
alert_message_id = None


# ================== КЛАВИАТУРЫ ==================

def get_status_keyboard():
    notif_text = "🔔 Уведомления: ВКЛ" if NOTIFICATIONS_ENABLED else "🔕 Уведомления: ВЫКЛ"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=notif_text, callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="🔄 Сменить кабинет", callback_data="change_cabinet")]
    ])


def get_cabinet_keyboard():
    buttons = [
        InlineKeyboardButton(
            text=cab,
            callback_data=f"cabinet_{cab}"
        )
        for cab in AVAILABLE_CABINETS
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[i:i+2] for i in range(0, len(buttons), 2)]
    )


# ================== /start ==================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    global SELECTED_CABINET
    SELECTED_CABINET = None

    await message.answer(
        "Выберите кабинет:",
        reply_markup=get_cabinet_keyboard()
    )


# ================== ВЫБОР КАБИНЕТА ==================

@dp.callback_query(F.data.startswith("cabinet_"))
async def cabinet_selected(callback: types.CallbackQuery):
    global SELECTED_CABINET, alert_message_id

    SELECTED_CABINET = callback.data.replace("cabinet_", "")
    alert_message_id = None

    await callback.answer("Кабинет выбран")

    text = (
        f"⚪ Состояние кабинета\n\n"
        f"Дата: —\n"
        f"Время: —\n\n"
        f"🫁 CO₂: — ppm\n"
        f"🌡 Температура: — °C\n"
        f"💧 Влажность: — %\n\n"
        f"Ожидание данных..."
    )

    msg = await bot.send_message(
        CHAT_ID,
        text,
        reply_markup=get_status_keyboard()
    )

    # сохранить message_id
    cursor.execute(
        "INSERT OR IGNORE INTO devices (device_uid, api_key) VALUES (?, ?)",
        (SELECTED_CABINET, "")
    )

    cursor.execute(
        "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
        (msg.message_id, SELECTED_CABINET)
    )

    conn.commit()


# ================== ПЕРЕКЛЮЧЕНИЕ УВЕДОМЛЕНИЙ ==================

@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: types.CallbackQuery):
    global NOTIFICATIONS_ENABLED

    NOTIFICATIONS_ENABLED = not NOTIFICATIONS_ENABLED

    await callback.answer("Настройки обновлены")

    # обновим кнопки без изменения текста
    try:
        await bot.edit_message_reply_markup(
            CHAT_ID,
            callback.message.message_id,
            reply_markup=get_status_keyboard()
        )
    except:
        pass


# ================== СМЕНА КАБИНЕТА ==================

@dp.callback_query(F.data == "change_cabinet")
async def change_cabinet(callback: types.CallbackQuery):
    global SELECTED_CABINET, alert_message_id

    SELECTED_CABINET = None

    # удалить сообщение состояния
    try:
        await bot.delete_message(CHAT_ID, callback.message.message_id)
    except:
        pass

    # удалить alert
    if alert_message_id:
        try:
            await bot.delete_message(CHAT_ID, alert_message_id)
        except:
            pass
        alert_message_id = None

    await bot.send_message(
        CHAT_ID,
        "Выберите кабинет:",
        reply_markup=get_cabinet_keyboard()
    )


# ================== ОБНОВЛЕНИЕ СООБЩЕНИЯ ==================

async def send_or_update(uid, text):
    cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
    row = cursor.fetchone()

    keyboard = get_status_keyboard()

    if row and row[0]:
        try:
            await bot.edit_message_text(
                text,
                CHAT_ID,
                row[0],
                reply_markup=keyboard
            )
            return
        except:
            pass

    msg = await bot.send_message(
        CHAT_ID,
        text,
        reply_markup=keyboard
    )

    cursor.execute(
        "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
        (msg.message_id, uid)
    )
    conn.commit()


# ================== МОНИТОРИНГ ==================

async def monitor():
    global SELECTED_CABINET, alert_message_id

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

        # ===== УВЕДОМЛЕНИЯ =====
        if not status_ok and NOTIFICATIONS_ENABLED:
            if alert_message_id:
                try:
                    await bot.delete_message(CHAT_ID, alert_message_id)
                except:
                    pass

            msg = await bot.send_message(
                CHAT_ID,
                "⚠️ Внимание! Параметры не в норме!"
            )
            alert_message_id = msg.message_id

        await asyncio.sleep(120)  # каждые 2 минуты


# ================== MAIN ==================

async def main():
    asyncio.create_task(monitor())
    asyncio.create_task(dp.start_polling(bot))
