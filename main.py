import os
import time
import requests
from telegram import Bot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TOKEN)
last_status = None

def check_cursor_ai():
    try:
        url = "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {"role": "user", "content": "ping"}
            ],
            "model": "gpt-4",
        }
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

while True:
    status = check_cursor_ai()
    if status != last_status:
        if status:
            bot.send_message(chat_id=CHAT_ID, text="✅ Cursor AI is RESPONDING")
        else:
            bot.send_message(chat_id=CHAT_ID, text="❌ Cursor AI is NOT responding")
        last_status = status
    time.sleep(300)  # כל 5 דקות
