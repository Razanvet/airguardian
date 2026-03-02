import asyncio
import sqlite3
from aiogram import Bot, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.event.dispatcher import Dispatcher

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = 1200659505

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()  # В 3.x Dispatcher не принимает bot в конструкторе

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}
last_sent_id = {}
SELECTED_CABINET = None
AVAILABLE_CABINETS = ["cabinet_101"]  # пока только один активен
notifications_enabled = True
last_alert_msg_id = None

# ===== Функции =====
async def send_or_update_message(text: str, uid: str):
    try:
        cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (uid,))
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        if msg_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg_id, text=text,
                                            reply_markup=get_main_keyboard())
                return msg_id
            except:
                print(f"⚠ Не удалось редактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text, reply_markup=get_main_keyboard())
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (msg.message_id, uid))
        conn.commit()
        return msg.message_id
    except Exception as e:
        print("Telegram error:", e)
        return None

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            text=f"Уведомления {'✅' if notifications_enabled else '❌'}",
            callback_data="toggle_notifications"
        ),
        InlineKeyboardButton(
            text="Сменить кабинет",
            callback_data="change_cabinet"
        )
    )
    return keyboard

async def monitor_new_measurements():
    global last_alert_msg_id
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
                # Если данных ещё нет, показываем пустые значения
                text = "Ожидание данных...\nCO2: N/A\nТемпература: N/A\nВлажность: N/A"
                await send_or_update_message(text, uid)
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
                f"🫁 CO₂: {co2}\n"
                f"🌡 Температура: {temp}\n"
                f"💧 Влажность: {hum}\n\n"
                f"{status_text}"
            )

            msg_id = await send_or_update_message(text, uid)
            last_sent_id[uid] = meas_id

            # ===== Отдельные уведомления каждые 2 минуты =====
            if notifications_enabled and not status_ok:
                if last_alert_msg_id:
                    try:
                        await bot.delete_message(chat_id=CHAT_ID, message_id=last_alert_msg_id)
                    except:
                        pass
                alert = await bot.send_message(CHAT_ID, "⚠ Внимание! Параметры не в норме!")
                last_alert_msg_id = alert.message_id
                await asyncio.sleep(120)

            await asyncio.sleep(1)
        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== Callback =====
@dp.callback_query()
async def handle_callback(query: types.CallbackQuery):
    global SELECTED_CABINET, notifications_enabled, last_alert_msg_id
    data = query.data

    if data == "toggle_notifications":
        notifications_enabled = not notifications_enabled
        await query.answer(text=f"Уведомления {'включены' if notifications_enabled else 'выключены'}")
        # Обновляем сообщение с состоянием
        if SELECTED_CABINET:
            await send_or_update_message("Обновление состояния...", SELECTED_CABINET)

    elif data == "change_cabinet":
        # Удаляем текущее сообщение и возвращаемся к выбору
        try:
            cursor.execute("SELECT tg_message_id FROM devices WHERE device_uid=?", (SELECTED_CABINET,))
            row = cursor.fetchone()
            if row and row[0]:
                await bot.delete_message(chat_id=CHAT_ID, message_id=row[0])
        except:
            pass
        SELECTED_CABINET = None
        await query.answer("Выберите кабинет:")
        keyboard = InlineKeyboardMarkup(row_width=2)
        buttons = [InlineKeyboardButton(text=cab, callback_data=cab) for cab in AVAILABLE_CABINETS]
        keyboard.add(*buttons)
        await bot.send_message(CHAT_ID, "Выберите кабинет:", reply_markup=keyboard)
    elif data in AVAILABLE_CABINETS:
        SELECTED_CABINET = data
        await query.answer(f"Выбран {SELECTED_CABINET}")
        await send_or_update_message("Ожидание данных...", SELECTED_CABINET)

# ===== Запуск бота =====
async def main():
    asyncio.create_task(monitor_new_measurements())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
