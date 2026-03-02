# bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== Хранилище состояния пользователей =====
# user_id -> {"cabinet": int, "notifications": bool, "last_alert_msg": Message}
user_state = {}

# ===== Функции клавиатур =====
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

# ===== Обработка кнопок выбора кабинета =====
@dp.callback_query(lambda c: c.data and c.data.startswith("cabinet_"))
async def select_cabinet(query: types.CallbackQuery):
    user_id = query.from_user.id
    cabinet_number = int(query.data.split("_")[1])
    state = user_state.get(user_id, {"notifications": False})
    state["cabinet"] = cabinet_number
    state["notifications"] = False
    state["last_alert_msg"] = None
    user_state[user_id] = state

    await query.message.edit_text(
        f"Вы выбрали кабинет {cabinet_number}.\nОжидание данных...",
        reply_markup=main_buttons(state["notifications"])
    )
    await query.answer()

# ===== Основные кнопки =====
@dp.callback_query(Text(["toggle_notifications", "change_cabinet"]))
async def handle_main_buttons(query: types.CallbackQuery):
    user_id = query.from_user.id
    state = user_state.get(user_id)
    if not state:
        await query.answer("Ошибка состояния пользователя")
        return

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

# ===== Функция для обновления состояния кабинета =====
async def update_cabinet_status(cabinet: int, co2=None, temperature=None, humidity=None):
    for user_id, state in user_state.items():
        if state.get("cabinet") != cabinet:
            continue

        text = (
            f"Кабинет {cabinet}:\n"
            f"CO2: {co2 if co2 is not None else '-'} ppm\n"
            f"Температура: {temperature if temperature is not None else '-'} °C\n"
            f"Влажность: {humidity if humidity is not None else '-'} %"
        )

        try:
            if state["last_alert_msg"]:
                await state["last_alert_msg"].edit_text(text, reply_markup=main_buttons(state["notifications"]))
            else:
                msg = await bot.send_message(CHAT_ID, text, reply_markup=main_buttons(state["notifications"]))
                state["last_alert_msg"] = msg
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")

# ===== Уведомление о критических значениях =====
async def send_alert(cabinet: int):
    for user_id, state in user_state.items():
        if state.get("cabinet") != cabinet or not state.get("notifications"):
            continue
        try:
            alert_text = "⚠️ Внимание! Параметры не в норме!"
            if state.get("last_alert_msg"):
                await state["last_alert_msg"].delete()
            msg = await bot.send_message(CHAT_ID, alert_text)
            state["last_alert_msg"] = msg
            await asyncio.sleep(120)
            await msg.delete()
        except Exception as e:
            print(f"Ошибка alert: {e}")

# ===== Запуск бота =====
async def main():
    print("Bot started")
    await dp.start_polling(bot)

# Для интеграции с main.py
