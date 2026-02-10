import sqlite3
import asyncio
import math
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

# ===== Настройки бота =====
TELEGRAM_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = "1200659505"

# ===== Инициализация бота =====
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# ===== База данных =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# ===== Пороговые значения =====
LIMITS = {
    "co2": {"min": 400, "max": 1000},
    "temperature": {"min": 18, "max": 27},
    "humidity": {"min": 30, "max": 70}
}

# ===== Параметры класса =====
L, W, H = 8.0, 6.0, 3.0
V = L * W * H
N = 20

# ===== Окна =====
num_windows = 4
W_win, H_win = 1.5, 1.2
h_open = 0.08
C_d = 0.6

# ===== Внешние условия =====
T_out = -5   # температура на улице
v_wind = 3   # скорость ветра м/с
RH_out = 50  # наружная влажность %

# ===== Радиаторы =====
P_rad = 2000   # Вт
rho_air = 1.2  # кг/м³
C_rad = 0.6
T_battery = 35  # температура батареи

# ===== Функция отправки или обновления сообщений =====
async def send_or_update_message(text: str, message_id: int | None = None) -> int:
    try:
        if message_id:
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=message_id, text=text)
                return message_id
            except TelegramAPIError:
                msg = await bot.send_message(chat_id=CHAT_ID, text=text)
                return msg.message_id
        else:
            msg = await bot.send_message(chat_id=CHAT_ID, text=text)
            return msg.message_id
    except Exception as e:
        print("Telegram send error:", e)
        return message_id or 0

# ===== Расчёт времени до нормализации =====
def calculate_recovery_times(co2, temp, hum):
    # ----- Реальный поток с вентиляцией и отоплением -----
    delta_T = temp - T_out
    T_avg = (temp + T_out)/2 + 273.15
    v_stack = math.sqrt(2 * 9.81 * H_win * (delta_T / T_avg))
    v_rad = C_rad * (P_rad / (rho_air * V))**(1/3)
    v_eff = math.sqrt(v_stack**2 + v_wind**2 + v_rad**2)

    A_open = W_win * h_open
    Q_per_window = C_d * A_open * v_eff
    Q_window = Q_per_window * num_windows * 3600  # м³/ч

    # ----- Время по CO2 -----
    C_current = co2
    C_max = LIMITS["co2"]["max"]
    C_outside = LIMITS["co2"]["min"]  # для расчета
    G = N * 0.005  # генерация CO2 на человека
    Q_CO2 = G / ((C_max - C_outside) * 1e-6)
    t_CO2_h = - (V / Q_window) * math.log((C_max - C_outside)/(C_current - C_outside))

    # ----- Время по температуре -----
    T_min = LIMITS["temperature"]["min"]
    # Простая модель отопления + вентиляция
    t_temp_h = - (V / Q_window) * math.log((T_min - T_out)/(temp - T_out))

    # ----- Время по влажности -----
    RH_min = LIMITS["humidity"]["min"]
    RH_in = hum
    t_rh_h = - (V / Q_window) * math.log((RH_min - RH_out)/(RH_in - RH_out))

    # ----- Предельное время -----
    t_vent_h = min(t_CO2_h, t_temp_h, t_rh_h)
    t_vent_min = t_vent_h * 60
    return Q_window, Q_CO2, t_vent_min

# ===== Проверка всех устройств =====
async def check_all_devices():
    cursor.execute("SELECT device_uid, tg_message_id FROM devices")
    devices = cursor.fetchall()

    for device_uid, message_id in devices:
        cursor.execute("""
            SELECT co2, temperature, humidity, timestamp
            FROM measurements
            WHERE device_uid=?
            ORDER BY id DESC
            LIMIT 1
        """, (device_uid,))
        row = cursor.fetchone()
        if not row:
            continue

        co2, temp, hum, ts = row
        Q_window, Q_CO2, t_vent_min = calculate_recovery_times(co2, temp, hum)

        # ----- Формируем текст -----
        text = (
            f"🟢 *Состояние кабинета*\n"
            f"Кабинет: `{device_uid}`\n"
            f"Время: {ts}\n\n"
            f"*Данные:*\n"
            f"CO₂: {co2} ppm{' ❗' if co2 > LIMITS['co2']['max'] else ''}\n"
            f"Температура: {temp:.1f} °C{' ❗' if temp < LIMITS['temperature']['min'] else ''}\n"
            f"Влажность: {hum:.1f} %{' ❗' if hum < LIMITS['humidity']['min'] else ''}\n\n"
            f"Реальный поток вентиляции: {Q_window:.1f} м³/ч\n"
            f"Необходимый поток: {Q_CO2:.1f} м³/ч\n"
            f"Время до нормализации: {t_vent_min:.0f} мин"
        )

        # ----- Отправка или обновление -----
        new_message_id = await send_or_update_message(text, message_id)
        cursor.execute("UPDATE devices SET tg_message_id=? WHERE device_uid=?", (new_message_id, device_uid))
        conn.commit()

# ===== Главный цикл =====
async def main_loop():
    while True:
        await check_all_devices()
        await asyncio.sleep(60)

# ===== Запуск =====
if __name__ == "__main__":
    asyncio.run(main_loop())
