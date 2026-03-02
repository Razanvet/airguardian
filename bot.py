# bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== Хранилище состояния пользователей =====
user_state = {}  # user_id -> {"cabinet": int, "notifications": bool, "last_alert_msg": Message}

# ===== Очередь для поступающих данных от ESP32 =====
data_queue = asyncio.Queue()  # сюда main.py будет класть данные

# ===== Клавиатуры =====
def cabinet_selection_buttons():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Кабинет {i}", callback_data=f"cabinet_{i}")]
            for i in range(101, 111)
        ]
    )
    return keyboard

def main_buttons(notifications_on: bool):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔔 Выключить уведомления" if notifications_on else "🔔 Включить уведомления",
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Сменить кабинет",
                    callback_data="change_cabinet"
                )
            ]
        ]
    )
    return keyboard

# ===== /start =====
@dp.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    user_state[message.from_user.id] = {"cabinet": None, "notifications": False, "last_alert_msg": None}
    await message.answer(
        "Выберите кабинет:",
        reply_markup=cabinet_selection_buttons()
    )

# ===== Выбор кабинета =====
@dp.callback_query(lambda c: c.data and c.data.startswith("cabinet_"))
async def select_cabinet(query: types.CallbackQuery):
    user_id = query.from_user.id
    cabinet_number = int(query.data.split("_")[1])

    state = user_state.get(user_id)
    if not state:
        state = {"cabinet": cabinet_number, "notifications": False, "last_alert_msg": query.message}
    else:
        state["cabinet"] = cabinet_number
        state["notifications"] = False

    msg = await query.message.edit_text(
        f"Вы выбрали кабинет {cabinet_number}.\nОжидание данных...",
        reply_markup=main_buttons(state["notifications"])
    )
    state["last_alert_msg"] = msg
    user_state[user_id] = state
    await query.answer()

# ===== Основные кнопки =====
@dp.callback_query(lambda c: c.data in ["toggle_notifications", "change_cabinet"])
async def handle_main_buttons(query: types.CallbackQuery):
    user_id = query.from_user.id
    state = user_state.get(user_id)
    if not state:
        state = {"cabinet": None, "notifications": False, "last_alert_msg": query.message}
        user_state[user_id] = state

    if query.data == "toggle_notifications":
        state["notifications"] = not state["notifications"]
        await query.message.edit_reply_markup(reply_markup=main_buttons(state["notifications"]))
        await query.answer("Уведомления включены" if state["notifications"] else "Уведомления выключены")

    elif query.data == "change_cabinet":
        state["cabinet"] = None
        state["last_alert_msg"] = None
        await query.message.edit_text(
            "Выберите новый кабинет:",
            reply_markup=cabinet_selection_buttons()
        )

# ===== Обновление данных кабинета =====
async def update_cabinet_status(cabinet: int, co2: float, temperature: float, humidity: float):
    for user_id, state in user_state.items():
        if state.get("cabinet") != cabinet:
            continue
        text = (
            f"Кабинет {cabinet}:\n"
            f"CO2: {co2} ppm\n"
            f"Температура: {temperature} °C\n"
            f"Влажность: {humidity} %"
        )
        try:
            if state.get("last_alert_msg"):
                await state["last_alert_msg"].edit_text(text, reply_markup=main_buttons(state["notifications"]))
            else:
                msg = await bot.send_message(user_id, text, reply_markup=main_buttons(state["notifications"]))
                state["last_alert_msg"] = msg
        except Exception as e:
            print(f"Ошибка обновления данных пользователя {user_id}: {e}")

# ===== Alert =====
async def send_alert(cabinet: int, alert_text: str):
    for user_id, state in user_state.items():
        if state.get("cabinet") != cabinet or not state.get("notifications"):
            continue
        try:
            msg = await bot.send_message(user_id, f"⚠️ {alert_text}")
            state["last_alert_msg"] = msg
        except Exception as e:
            print(f"Ошибка отправки alert пользователю {user_id}: {e}")

# ===== Фоновая задача: слушаем очередь данных =====
async def process_queue():
    while True:
        data = await data_queue.get()
        cabinet = data.get("cabinet")
        co2 = data.get("co2")
        temperature = data.get("temperature")
        humidity = data.get("humidity")
        await update_cabinet_status(cabinet, co2, temperature, humidity)
        # Пример alert
        if co2 > 1000:
            await send_alert(cabinet, "CO2 слишком высокий!")

# ===== Запуск бота =====
async def main():
    asyncio.create_task(process_queue())
    await dp.start_polling(bot)
