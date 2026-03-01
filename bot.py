import asyncio
import sqlite3
import math
from aiogram import Bot, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.dispatcher import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(bot)

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}

# ===== Глобальные состояния =====
SELECTED_CABINET = None
AVAILABLE_CABINETS = [f"cabinet_{i}" for i in range(101, 111)]
last_sent_id = {}
notifications_enabled = False
alert_msg_id = None  # ID последнего уведомления об отклонении


# ===== Приветствие и выбор кабинета =====
@dp.message_handler(commands=["start"])
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


@dp.callback_query_handler(lambda c: c.data in AVAILABLE_CABINETS)
async def select_cabinet(callback_query: types.CallbackQuery):
    global SELECTED_CABINET, notifications_enabled
    if callback_query.data == "cabinet_101":
        SELECTED_CABINET = callback_query.data
        notifications_enabled = False
        await bot.answer_callback_query(callback_query.id, text=f"Выбран {SELECTED_CABINET}")
        await send_status_message(callback_query.from_user.id)
    else:
        await bot.answer_callback_query(callback_query.id, text="⚠️ Этот кабинет пока не работает", show_alert=True)


# ===== Кнопки состояния кабинета =====
def status_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    notif_text = "Уведомления 🔔 Вкл" if not notifications_enabled else "Уведомления 🔕 Выкл"
    keyboard.add(
        InlineKeyboardButton(text=notif_text, callback_data="toggle_notifications"),
        InlineKeyboardButton(text="Смена кабинета 🔄", callback_data="change_cabinet")
    )
    return keyboard


@dp.callback_query_handler(lambda c: c.data in ["toggle_notifications", "change_cabinet"])
async def handle_status_buttons(callback_query: types.CallbackQuery):
    global notifications_enabled, SELECTED_CABINET, alert_msg_id
    if callback_query.data == "toggle_notifications":
        notifications_enabled = not notifications_enabled
        await bot.answer_callback_query(callback_query.id, text=f"Уведомления {'включены' if notifications_enabled else 'выключены'}")
        # обновляем текст кнопки
        await send_status_message(callback_query.from_user.id)
    elif callback_query.data == "change_cabinet":
        if SELECTED_CABINET:
            # удаляем текущее сообщение с состоянием кабинета
            try:
                await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
            except Exception:
                pass
        SELECTED_CABINET = None
        alert_msg_id = None
        await start_command(callback_query.message)


# ===== Отправка сообщения о состоянии кабинета =====
async def send_status_message(user_id):
    if not SELECTED_CABINET:
        return

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
        return

    meas_id, co2, temp, hum, ts = row
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

    try:
        await bot.send_message(user_id, text, reply_markup=status_keyboard())
    except Exception as e:
        print("Error sending status message:", e)


# ===== Уведомления об отклонениях каждые 2 минуты =====
async def send_alerts(user_id):
    global alert_msg_id
    while True:
        if SELECTED_CABINET and notifications_enabled:
            uid = SELECTED_CABINET
            cursor.execute("""
                SELECT id, co2, temperature, humidity
                FROM measurements
                WHERE device_uid=?
                ORDER BY id DESC
                LIMIT 1
            """, (uid,))
            row = cursor.fetchone()
            if row:
                meas_id, co2, temp, hum = row
                status_ok = (co2 <= LIMITS["co2"] and temp >= LIMITS["temperature"] and hum >= LIMITS["humidity"])
                if not status_ok:
                    # удаляем старое уведомление
                    if alert_msg_id:
                        try:
                            await bot.delete_message(user_id, alert_msg_id)
                        except Exception:
                            pass
                    # отправляем новое уведомление
                    msg = await bot.send_message(user_id, "⚠️ Внимание! Параметры не в норме!")
                    alert_msg_id = msg.message_id
        await asyncio.sleep(120)  # повтор каждые 2 минуты


# ===== Мониторинг новых измерений (для обновления сообщения) =====
async def monitor_new_measurements(user_id):
    global last_sent_id
    while True:
        if SELECTED_CABINET:
            uid = SELECTED_CABINET
            cursor.execute("""
                SELECT id, co2, temperature, humidity, timestamp
                FROM measurements
                WHERE device_uid=?
                ORDER BY id DESC
                LIMIT 1
            """, (uid,))
            row = cursor.fetchone()
            if row:
                meas_id, co2, temp, hum, ts = row
                if last_sent_id.get(uid) != meas_id:
                    await send_status_message(user_id)
                    last_sent_id[uid] = meas_id
        await asyncio.sleep(1)


# ===== Запуск бота =====
async def main():
    try:
        # Запуск фоновых задач для каждого пользователя
        # Для школьного проекта пока запускаем только для одного пользователя (можно расширить)
        user_id = 1200659505  # замените на свой Telegram ID для теста
        asyncio.create_task(monitor_new_measurements(user_id))
        asyncio.create_task(send_alerts(user_id))
        await dp.start_polling()
    finally:
        await bot.session.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
