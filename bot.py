import asyncio
import sqlite3
import math
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

# ===== Telegram =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = "1200659505"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# ===== БД =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Параметры =====
LIMITS = {"co2": 1000, "temperature": 18, "humidity": 30}
L, W, H = 8, 6, 3
V = L * W * H
N = 20

num_windows = 4
W_win, H_win = 1.5, 1.2
h_open = 0.08
C_d = 0.6

T_out = -5
v_wind = 3
RH_out = 50

P_rad = 2000
rho_air = 1.2
C_rad = 0.6

# ===== Telegram =====
async def send_or_update_message(text, msg_id):
    try:
        if msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=msg_id,
                    text=text
                )
                return msg_id
            except TelegramAPIError as e:
                print("Edit error:", e)

        msg = await bot.send_message(CHAT_ID, text)
        return msg.message_id

    except Exception as e:
        print("Send error:", e)
        return msg_id


# ===== Расчёт =====
def calc_time(co2, temp, hum):
    delta_T = temp - T_out
    T_avg = (temp + T_out)/2 + 273.15
    v_stack = math.sqrt(2 * 9.81 * H_win * abs(delta_T) / T_avg)
    v_rad = C_rad * (P_rad / (rho_air * V)) ** (1/3)
    v = math.sqrt(v_stack**2 + v_wind**2 + v_rad**2)

    Q = C_d * W_win * h_open * v * num_windows * 3600

    t_co2 = V / Q if co2 > LIMITS["co2"] else float("inf")
    t_temp = V / Q if temp < LIMITS["temperature"] else float("inf")
    t_hum = V / Q if hum < LIMITS["humidity"] else float("inf")

    return Q, min(t_co2, t_temp, t_hum) * 60

# ===== Цикл =====
async def loop():
    while True:
        cursor.execute("""
            SELECT d.device_uid, d.tg_message_id,
                   m.co2, m.temperature, m.humidity, m.timestamp
            FROM devices d
            JOIN measurements m ON m.device_uid=d.device_uid
            WHERE m.id=(SELECT MAX(id) FROM measurements WHERE device_uid=d.device_uid)
        """)

        for uid, msg_id, co2, temp, hum, ts in cursor.fetchall():
            Q, t = calc_time(co2, temp, hum)

            text = (
                f"🟢 *Состояние кабинета*\n"
                f"Кабинет: `{uid}`\n"
                f"Время: {ts}\n\n"
                f"CO₂: {co2} ppm\n"
                f"🌡 Температура: {temp} °C\n"
                f"💧 Влажность: {hum} %\n\n"
                f"💨 Вентиляция: {Q:.0f} м³/ч\n"
                f"⏳ До нормы: {t:.0f} мин"
            )

            new_id = await send_or_update_message(text, msg_id)
            cursor.execute(
                "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
                (new_id, uid)
            )
            conn.commit()

        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(loop())

