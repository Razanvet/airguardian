import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from datetime import datetime, timedelta

# ===== Токен бота и ID чата =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Состояние пользователей =====
user_state = {}  # {user_id: {"cabinet": "cabinet_101", "notifications": True, "last_alert_msg": None}}

# ===== Кнопки =====
def cabinet_buttons():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Уведомления", callback_data="toggle_notifications")],
            [InlineKeyboardButton(text="Смена кабинета", callback_data="change_cabinet")]
        ]
    )
    return keyboard

# ===== Хендлер /start =====
@dp.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    user_state[message.from_user.id] = {"cabinet": None, "notifications": False, "last_alert_msg": None}
    await message.answer("Выберите кабинет (пока данные отсутствуют)", reply_markup=None)

# ===== Выбор кабинета =====
@dp.callback_query()
async def callback_handler(query: types.CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data.startswith("cabinet_"):
        user_state[user_id]["cabinet"] = data
        await query.message.edit_text(f"Кабинет {data} выбран.\nОжидание данных...", reply_markup=cabinet_buttons())

    elif data == "toggle_notifications":
        state = user_state[user_id]
        state["notifications"] = not state.get("notifications", False)
        status = "включены" if state["notifications"] else "выключены"
        await query.message.answer(f"Уведомления {status}")

    elif data == "change_cabinet":
        state = user_state[user_id]
        state["cabinet"] = None
        await query.message.edit_text("Выберите новый кабинет:", reply_markup=None)

    await query.answer()  # чтобы убрать "часики" Telegram

# ===== Отправка состояния кабинета =====
async def send_cabinet_status():
    while True:
        cursor.execute("SELECT * FROM measurements ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()

        for user_id, state in user_state.items():
            cabinet = state.get("cabinet")
            if not cabinet:
                continue

            if row:
                co2, temp, hum = row[2], row[3], row[4]
                text = (
                    f"Состояние кабинета {cabinet}:\n"
                    f"CO2: {co2}\n"
                    f"Температура: {temp}\n"
                    f"Влажность: {hum}"
                )
            else:
                text = f"Состояние кабинета {cabinet}:\nОжидание данных...\n---"

            try:
                await bot.send_message(user_id, text=text, reply_markup=cabinet_buttons())
            except Exception as e:
                print(f"Ошибка отправки статуса: {e}")

        await asyncio.sleep(30)  # обновление каждые 30 секунд

# ===== Отправка уведомлений =====
async def send_alerts():
    while True:
        cursor.execute("SELECT * FROM measurements ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()

        for user_id, state in user_state.items():
            if not state.get("notifications") or not state.get("cabinet"):
                continue

            if row:
                co2, temp, hum = row[2], row[3], row[4]
                alert_needed = co2 > 1000 or temp > 30 or hum > 70  # пример порогов

                if alert_needed:
                    last_msg = state.get("last_alert_msg")
                    text = f"⚠️ Внимание! Параметры не в норме!\nCO2: {co2}\nТемп: {temp}\nВлажность: {hum}"

                    # Удаляем предыдущее сообщение
                    if last_msg:
                        try:
                            await bot.delete_message(chat_id=user_id, message_id=last_msg)
                        except:
                            pass

                    # Отправляем новое
                    msg = await bot.send_message(user_id, text=text)
                    state["last_alert_msg"] = msg.message_id

        await asyncio.sleep(120)  # каждые 2 минуты

# ===== Основная точка запуска =====
async def main():
    # Запуск поллинга бота и задач
    await asyncio.gather(
        dp.start_polling(bot),
        send_cabinet_status(),
        send_alerts()
    )

if __name__ == "__main__":
    asyncio.run(main())
