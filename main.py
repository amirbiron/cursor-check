import os
import time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

last_status = None

def send(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        pass  # לא מפיל את הלולאה אם שליחת טלגרם נכשלה

def check_cursor_ai() -> bool:
    try:
        url = "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools"
        payload = {
            "messages": [{"role": "user", "content": "ping"}],
            "model": "gpt-4",
        }
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    global last_status
    while True:
        status = check_cursor_ai()
        if status != last_status:
            send("✅ Cursor AI is RESPONDING" if status else "❌ Cursor AI is NOT responding")
            last_status = status
        time.sleep(300)  # כל 5 דקות
