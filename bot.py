from telegram import Bot

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8552290162:AAGHM0pmC6BuCjE4NlTqG0N3pIGNZ4r4lCc"
CHAT_ID = "1200659505"

bot = Bot(token=BOT_TOKEN)

async def send_alert(message: str):
    print("DEBUG: send_alert called")
    await bot.send_message(
        chat_id=CHAT_ID,
        text=message
    )


