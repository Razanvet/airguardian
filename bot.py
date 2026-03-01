import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import exceptions
from datetime import datetime

BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Настройки кабинетов ---
CABINETS = [f"cabinet_{i}" for i in range(101, 111)]
WORKING_CABINET = "cabinet_101"
notifications_enabled = {}

# --- Состояние кабинета (пример) ---
# В реальности сюда нужно писать данные с вашего ESP32
cabinet_state = {
    "co2": 625,
    "temperature": 29.5,
    "humidity": 36.1
}

# --- Кнопки ---
def get_cabinet_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="🏫 Смена кабинета", callback_data="change_cabinet")]
    ])
    return kb

# --- Приветственное сообщение ---
@dp.message(Command(commands=["start"]))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"select_{c}") for c in CABINETS]
    ])
    await message.answer(
        "Привет! Выберите кабинет для мониторинга (пока работает только cabinet_101):",
        reply_markup=kb
    )

# --- Выбор кабинета ---
@dp.callback_query(F.data.startswith("select_"))
async def select_cabinet(query: CallbackQuery):
    cabinet = query.data.split("_")[1] + "_" + query.data.split("_")[2]
    if cabinet != WORKING_CABINET:
        await query.answer("Этот кабинет пока не поддерживается 😅", show_alert=True)
        return
    notifications_enabled[query.from_user.id] = False
    await query.message.delete()
    await send_cabinet_state(query.from_user.id)

# --- Отправка состояния кабинета ---
async def send_cabinet_state(user_id: int):
    co2 = cabinet_state["co2"]
    temp = cabinet_state["temperature"]
    hum = cabinet_state["humidity"]

    # Цвет кружка
    ok = (co2 < 800 and 18 <= temp <= 26 and 30 <= hum <= 60)
    status_emoji = "🟢" if ok else "🔴"

    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M:%S")

    text = (
        f"{status_emoji} Состояние кабинета:\n"
        f"📅 Дата: {date_str}\n"
        f"⏰ Время: {time_str}\n"
        f"💨 CO2: {co2} ppm\n"
        f"🌡 Температура: {temp:.1f}°C\n"
        f"💧 Влажность: {hum:.1f}%"
    )

    await bot.send_message(user_id, text, reply_markup=get_cabinet_keyboard())

# --- Кнопки уведомлений и смены кабинета ---
@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(query: CallbackQuery):
    current = notifications_enabled.get(query.from_user.id, False)
    notifications_enabled[query.from_user.id] = not current
    status = "включены" if not current else "выключены"
    await query.answer(f"Уведомления {status}")

@dp.callback_query(F.data == "change_cabinet")
async def change_cabinet(query: CallbackQuery):
    await query.message.delete()
    await cmd_start(Message(chat=query.message.chat, from_user=query.from_user, text="/start"))

# --- Фоновая проверка состояния кабинета и уведомлений ---
async def notify_loop():
    while True:
        for user_id, enabled in notifications_enabled.items():
            if enabled:
                # Если параметры не в норме
                co2 = cabinet_state["co2"]
                temp = cabinet_state["temperature"]
                hum = cabinet_state["humidity"]
                if co2 >= 800 or temp < 18 or temp > 26 or hum < 30 or hum > 60:
                    text = "⚠️ Внимание! Параметры не в норме!"
                    # Отправка нового сообщения каждые 2 минуты
                    try:
                        await bot.send_message(user_id, text)
                    except exceptions.TelegramBadRequest:
                        pass
        await asyncio.sleep(120)  # проверка каждые 2 минуты

# --- Запуск ---
async def main():
    asyncio.create_task(notify_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
