import os
import time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

last_status = None

def send(text: str):
    if not TOKEN or not CHAT_ID:
        print("❗ Missing env vars: TELEGRAM_BOT_TOKEN or CHAT_ID")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"❗ Telegram send failed: {resp.status_code} {resp.text}")
        else:
            print(f"✅ Sent to Telegram: {text}")
    except Exception as e:
        print(f"❗ Telegram exception: {e}")

def check_cursor_ai() -> bool:
    try:
        url = "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools"
        payload = {
            "messages": [{"role": "user", "content": "ping"}],
            "model": "gpt-4",
        }
        r = requests.post(url, json=payload, timeout=10)
        print(f"ℹ️ Cursor AI check -> {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"❗ Cursor AI check exception: {e}")
        return False

if __name__ == "__main__":
    # הודעת בדיקה בהפעלה כדי לוודא ש-Telegram עובד
    send("🤖 cursor-monitor started")

    while True:
        status = check_cursor_ai()
        if status != last_status:
            send("✅ Cursor AI is RESPONDING" if status else "❌ Cursor AI is NOT responding")
            last_status = status
        time.sleep(60)  # דקה בין בדיקות (אפשר להחזיר ל-300 אחרי שמוודאים שזה עובד)
