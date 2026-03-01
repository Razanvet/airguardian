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
num_windows = 4
W_win, H_win = 1.5, 1.2
h_open = 0.08
C_d = 0.6
T_out = -5
v_wind = 3
P_rad = 2000
rho_air = 1.2
C_rad = 0.6

# ===== Храним последний отправленный measurement id =====
last_sent_id = {}

# ===== Telegram =====
async def send_or_update_message(text: str, uid: str):
    try:
        cursor.execute(
            "SELECT tg_message_id FROM devices WHERE device_uid=?",
            (uid,)
        )
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        if msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=msg_id,
                    text=text
                )
                return msg_id
            except TelegramAPIError:
                print(f"⚠ Не удалось отредактировать сообщение {msg_id}, создаём новое")

        msg = await bot.send_message(CHAT_ID, text)

        cursor.execute(
            "UPDATE devices SET tg_message_id=? WHERE device_uid=?",
            (msg.message_id, uid)
        )
        conn.commit()

        return msg.message_id

    except Exception as e:
        print("Telegram error:", e)
        return None

# ===== Расчёт =====
def calc_time(co2, temp, hum):
    delta_T = temp - T_out
    T_avg = (temp + T_out) / 2 + 273.15

    v_stack = math.sqrt(
        2 * 9.81 * H_win * abs(delta_T) / T_avg
    ) if T_avg > 0 else 0

    v_rad = C_rad * (P_rad / (rho_air * V)) ** (1 / 3)

    v = math.sqrt(v_stack**2 + v_wind**2 + v_rad**2)

    Q = C_d * W_win * h_open * v * num_windows * 3600

    if Q <= 0:
        return 0, 0

    t_co2 = V / Q if co2 > LIMITS["co2"] else float("inf")
    t_temp = V / Q if temp < LIMITS["temperature"] else float("inf")
    t_hum = V / Q if hum < LIMITS["humidity"] else float("inf")

    t_min = min(t_co2, t_temp, t_hum)

    if math.isinf(t_min):
        t_min = 0
    else:
        t_min *= 60

    return Q, t_min

# ===== Мониторинг =====
async def monitor_new_measurements():
    while True:
        try:
            cursor.execute("SELECT device_uid FROM devices")
            devices = [row[0] for row in cursor.fetchall()]

            for uid in devices:
                cursor.execute("""
                    SELECT id, co2, temperature, humidity, timestamp
                    FROM measurements
                    WHERE device_uid=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (uid,))
                row = cursor.fetchone()

                if not row:
                    continue

                meas_id, co2, temp, hum, ts = row

                if last_sent_id.get(uid) == meas_id:
                    continue

                Q, t = calc_time(co2, temp, hum)
                status = (
                    "✅ Параметры в норме"
                    if t == 0
                    else f"⏳ До нормы: {t:.0f} мин"
                )

                text = (
                    f"🟢 *Состояние кабинета*\n"
                    f"Кабинет: `{uid}`\n"
                    f"Время: {ts}\n\n"
                    f"CO₂: {co2} ppm\n"
                    f"🌡 Температура: {temp if temp is not None else 'N/A'} °C\n"
                    f"💧 Влажность: {hum if hum is not None else 'N/A'} %\n\n"
                    f"💨 Вентиляция: {Q:.0f} м³/ч\n"
                    f"{status}"
                )

                msg_id = await send_or_update_message(text, uid)
                if msg_id:
                    last_sent_id[uid] = meas_id

            await asyncio.sleep(1)

        except Exception as e:
            print("Monitor error:", e)
            await asyncio.sleep(5)

# ===== ВАЖНО: функция для FastAPI =====
async def loop():
    print("🚀 Telegram bot started")
    await monitor_new_measurements()
