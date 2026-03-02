# bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== Состояние пользователей =====
user_state = {}  
# user_id -> {
#   "cabinet": int,
#   "notifications": bool,
#   "last_message": Message,
#   "alert_active": bool
# }

# ===== Очередь данных от сервера =====
data_queue = asyncio.Queue()

# ===== Клавиатуры =====
def cabinet_selection_buttons():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Кабинет {i}", callback_data=f"cabinet_{i}")]
            for i in range(101, 111)
        ]
    )

def main_buttons(notifications_on: bool):
    return InlineKeyboardMarkup(
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

# ===== Проверка нормы =====
def check_status(co2, temp, hum):
    co2_ok = co2 <= 800
    temp_ok = 20 <= temp <= 25
    hum_ok = 30 <= hum <= 60

    return {
        "co2": "В норме ✅" if co2_ok else "Не в норме ⚠️",
        "temp": "В норме ✅" if temp_ok else "Не в норме ⚠️",
        "hum": "В норме ✅" if hum_ok else "Не в норме ⚠️",
        "overall": co2_ok and temp_ok and hum_ok
    }

# ===== /start =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_state[message.from_user.id] = {
        "cabinet": None,
        "notifications": False,
        "last_message": None,
        "alert_active": False
    }

    await message.answer(
        "Выберите кабинет:",
        reply_markup=cabinet_selection_buttons()
    )

# ===== Выбор кабинета =====
@dp.callback_query(lambda c: c.data.startswith("cabinet_"))
async def select_cabinet(query: types.CallbackQuery):
    user_id = query.from_user.id
    cabinet = int(query.data.split("_")[1])

    state = user_state.get(user_id)
    if not state:
        state = {
            "cabinet": cabinet,
            "notifications": False,
            "last_message": None,
            "alert_active": False
        }
    else:
        state["cabinet"] = cabinet
        state["alert_active"] = False

    text = f"Кабинет {cabinet}\nОжидание данных..."

    msg = await query.message.edit_text(
        text,
        reply_markup=main_buttons(state["notifications"])
    )

    state["last_message"] = msg
    user_state[user_id] = state

    await query.answer()

# ===== Основные кнопки =====
@dp.callback_query(lambda c: c.data in ["toggle_notifications", "change_cabinet"])
async def handle_buttons(query: types.CallbackQuery):
    user_id = query.from_user.id
    state = user_state[user_id]

    if query.data == "toggle_notifications":
        state["notifications"] = not state["notifications"]
        await query.message.edit_reply_markup(
            reply_markup=main_buttons(state["notifications"])
        )
        await query.answer("Уведомления включены" if state["notifications"] else "Уведомления выключены")

    elif query.data == "change_cabinet":
        state["cabinet"] = None
        state["alert_active"] = False
        await query.message.edit_text(
            "Выберите новый кабинет:",
            reply_markup=cabinet_selection_buttons()
        )

# ===== Alert цикл (без рекурсии!) =====
async def alert_loop(user_id, cabinet):
    while user_state.get(user_id, {}).get("alert_active", False):
        try:
            msg = await bot.send_message(
                user_id,
                f"⚠️ Параметры кабинета {cabinet} вне нормы!"
            )

            await asyncio.sleep(60)
            await msg.delete()

        except Exception as e:
            print(f"Alert error: {e}")
            break

# ===== Обновление данных =====
async def update_cabinet_status(cabinet, co2, temperature, humidity, timestamp):
    for user_id, state in user_state.items():
        if state["cabinet"] != cabinet:
            continue

        status = check_status(co2, temperature, humidity)

        text = (
            f"Кабинет {cabinet}\n\n"
            f"CO2: {co2} ppm — {status['co2']}\n"
            f"Температура: {temperature} °C — {status['temp']}\n"
            f"Влажность: {humidity} % — {status['hum']}\n\n"
            f"Последнее обновление: {timestamp}"
        )

        try:
            if state["last_message"]:
                await state["last_message"].edit_text(
                    text,
                    reply_markup=main_buttons(state["notifications"])
                )

            # ===== Управление уведомлениями =====
            if state["notifications"]:
                if not status["overall"]:
                    if not state["alert_active"]:
                        state["alert_active"] = True
                        asyncio.create_task(alert_loop(user_id, cabinet))
                else:
                    state["alert_active"] = False

        except Exception as e:
            print(f"Update error: {e}")

# ===== Обработка очереди =====
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

# ===== Запуск =====
async def main():
    asyncio.create_task(process_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
