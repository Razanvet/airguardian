from telegram import Bot

BOT_TOKEN = "ВАШ_BOT_TOKEN"
CHAT_ID = ВАШ_CHAT_ID

bot = Bot(token=BOT_TOKEN)

async def send_or_update_message(text: str, message_id: int | None):
    if message_id is None:
        msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode="Markdown"
        )
        return msg.message_id
    else:
        await bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=message_id,
            text=text,
            parse_mode="Markdown"
        )
        return message_id
