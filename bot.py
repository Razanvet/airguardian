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
data_queue = asyncio.Queue()

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

# ===== Проверка нормы =====
def check_status(co2, temp, hum):
    co2_ok = co2 <= 800
    temp_ok = 20 <= temp <= 25
    hum_ok = 30 <= hum <= 60
    overall_ok = co2_ok and temp_ok and hum_ok
    return {
        "co2": "В норме ✅" if co2_ok else "Не в норме ⚠️",
        "temp": "В норме ✅" if temp_ok else "Не в норме ⚠️",
        "hum": "В норме ✅" if hum_ok else "Не в норме ⚠️",
        "overall": overall_ok
    }

# ===== Выбор кабинета =====
@dp.callback_query(lambda c: c.data and c.data.startswith("cabinet_"))
async def select_cabinet(query: types.CallbackQuery):
    user_id = query.from_user.id
    cabinet_number = int(query.data.split("_")[1])

    state = user_state.get(user_id)
    if not state:
        state = {"cabinet": cabinet_number, "notifications": False, "last_alert_msg": None}
    else:
        state["cabinet"] = cabinet_number
        state["notifications"] = False

    # Проверяем, есть ли уже данные для этого кабинета в очереди
    latest_data = None
    for item in list(data_queue._queue):
        if item.get("cabinet") == cabinet_number:
            latest_data = item
    if latest_data:
        status = check_status(latest_data['co2'], latest_data['temperature'], latest_data['humidity'])
        text = (
            f"Кабинет {cabinet_number}:\n"
            f"CO2: {latest_data['co2']} ppm — {status['co2']}\n"
            f"Температура: {latest_data['temperature']} °C — {status['temp']}\n"
            f"Влажность: {latest_data['humidity']} % — {status['hum']}\n"
            f"Последнее обновление: {latest_data.get('timestamp', '—')}"
        )
    else:
        text = f"Вы выбрали кабинет {cabinet_number}.\nОжидание данных..."

    msg = await query.message.edit_text(
        text,
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
async def update_cabinet_status(cabinet: int, co2: float, temperature: float, humidity: float, timestamp: str):
    for user_id, state in user_state.items():
        if state.get("cabinet") != cabinet:
            continue

        status = check_status(co2, temperature, humidity)
        text = (
            f"Кабинет {cabinet}:\n"
            f"CO2: {co2} ppm — {status['co2']}\n"
            f"Температура: {temperature} °C — {status['temp']}\n"
            f"Влажность: {humidity} % — {status['hum']}\n"
            f"Последнее обновление: {timestamp}"
        )

        try:
            if state.get("last_alert_msg"):
                await state["last_alert_msg"].edit_text(text, reply_markup=main_buttons(state["notifications"]))
            else:
                msg = await bot.send_message(user_id, text, reply_markup=main_buttons(state["notifications"]))
                state["last_alert_msg"] = msg

            # Уведомления при отклонении
            if state["notifications"] and not status["overall"]:
                asyncio.create_task(send_alert_repeat(user_id, f"⚠️ Параметры кабинета {cabinet} вне нормы!"))
        except Exception as e:
            print(f"Ошибка обновления данных пользователя {user_id}: {e}")

# ===== Уведомления с повтором =====
async def send_alert_repeat(user_id, alert_text):
    try:
        msg = await bot.send_message(user_id, alert_text)
        await asyncio.sleep(60)
        await msg.delete()
        await asyncio.sleep(0.1)
        asyncio.create_task(send_alert_repeat(user_id, alert_text))
    except Exception as e:
        print(f"Ошибка уведомления пользователя {user_id}: {e}")

# ===== Фоновая задача: слушаем очередь данных =====
async def process_queue():
    while True:
        data = await data_queue.get()
        await update_cabinet_status(
            cabinet=data["cabinet"],
            co2=data["co2"],
            temperature=data["temperature"],
            humidity=data["humidity"],
            timestamp=data.get("timestamp", "—")
        )

# ===== Запуск бота =====
async def main():
    asyncio.create_task(process_queue())
    await dp.start_polling(bot)
