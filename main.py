import os, time, requests
from activity_reporter import create_reporter  # ← הוספה

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# מומלץ: לשים את ה-URI כ-ENV ולא בקוד
MONGODB_URI = os.getenv("MONGODB_URI")  # שים ב-Render → Environment
reporter = create_reporter(
    mongodb_uri=MONGODB_URI,
    service_id="srv-d2sbg924d50c73as1ku0",
    service_name="Cursor-Check"
)

last_status = None

def send(text: str, user_id: str = None):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text}, timeout=10
        )
        if user_id:
            reporter.report_activity(user_id)  # דיווח פעילות
    except Exception:
        pass

def check_cursor_ai() -> bool:
    try:
        r = requests.post(
            "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools",
            json={"messages":[{"role":"user","content":"ping"}], "model":"gpt-4"},
            timeout=10
        )
        return r.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    send("🤖 cursor-monitor started", user_id="monitor")
    while True:
        status = check_cursor_ai()
        if status != last_status:
            send("✅ Cursor AI is RESPONDING" if status else "❌ Cursor AI is NOT responding",
                 user_id="monitor")
            last_status = status
        time.sleep(60)
