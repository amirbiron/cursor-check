import os
import time
import requests
from activity_reporter import create_reporter

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

MONGODB_URI = os.getenv("MONGODB_URI")
reporter = create_reporter(
    mongodb_uri=MONGODB_URI,
    service_id="srv-d2sbg924d50c73as1ku0",
    service_name="Cursor-Check"
)

# --- seed ראשוני: שהשירות יופיע מיד בבוט ההשעיה ---
try:
    reporter.report_service_heartbeat()
except Exception:
    pass

last_status = None
HEARTBEAT_EVERY_MIN = 30
tick = 0

def send(text: str, user_id: str = None):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
        if user_id:
            # אם תרצה לרשום גם אינטראקציה של "משתמש־מערכת":
            # reporter.report_activity(user_id)
            pass
    except Exception:
        pass

def check_cursor_ai() -> bool:
    try:
        r = requests.post(
            "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools",
            json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    send("🤖 cursor-monitor started")
    while True:
        status = check_cursor_ai()

        if status != last_status:
            send("✅ Cursor AI is RESPONDING" if status else "❌ Cursor AI is NOT responding")
            last_status = status
            # אפשר גם לעדכן heartbeat בעת שינוי סטטוס:
            try:
                reporter.report_service_heartbeat()
            except Exception:
                pass

        # heartbeat תקופתי כל 30 דק׳
        tick += 1
        if tick >= HEARTBEAT_EVERY_MIN:
            try:
                reporter.report_service_heartbeat()
            except Exception:
                pass
            tick = 0

        time.sleep(60)
