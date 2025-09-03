import os
import time
import threading
import requests
from activity_reporter import create_reporter  # דיווח פעילות

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # לקבלת נוטיפיקציות מהניטור

MONGODB_URI = os.getenv("MONGODB_URI")
SERVICE_ID = os.getenv("SERVICE_ID", "srv-d2sbg924d50c73as1ku0")
SERVICE_NAME = os.getenv("SERVICE_NAME", "Cursor-Check")

# reporter
reporter = None
if MONGODB_URI:
    try:
        reporter = create_reporter(
            mongodb_uri=MONGODB_URI,
            service_id=SERVICE_ID,
            service_name=SERVICE_NAME,
        )
        print("✅ activity_reporter initialized")
    except Exception as e:
        print(f"❗ activity_reporter init failed: {e}")
else:
    print("ℹ️ MONGODB_URI not set – activity reporting disabled")

last_status = None
running = True  # מצב ניטור, נשלט ע״י פקודות

def send(text: str, chat_id: str = None, user_id: str | None = None):
    """שליחת הודעה לטלגרם + דיווח פעילות (אם אפשר)."""
    target = chat_id or CHAT_ID
    if not TOKEN or not target:
        print("❗ Missing TELEGRAM_BOT_TOKEN or chat_id")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": target, "text": text},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"❗ Telegram send failed: {resp.status_code} {resp.text}")
        else:
            print(f"✅ Sent: {text}")
            if reporter and user_id:
                try:
                    reporter.report_activity(user_id)
                except Exception as e:
                    print(f"❗ reporter.report_activity error: {e}")
    except Exception as e:
        print(f"❗ Telegram exception: {e}")

def check_cursor_ai() -> bool:
    """בודק אם ה-AI של Cursor מגיב (סטטוס 200)."""
    try:
        r = requests.post(
            "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools",
            json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
            timeout=10,
        )
        print(f"ℹ️ Cursor AI check -> {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"❗ Cursor AI check exception: {e}")
        return False

def monitor_loop():
    """לולאת הניטור (כל דקה) — שולחת נוטיפיקציה רק על שינוי מצב."""
    global last_status, running
    send("🤖 cursor-monitor started", user_id="monitor")
    while True:
        if running:
            status = check_cursor_ai()
            if status != last_status:
                send("✅ Cursor AI is RESPONDING" if status else "❌ Cursor AI is NOT responding",
                     user_id="monitor")
                last_status = status
        time.sleep(60)

def polling_loop():
    """
    Long polling פשוט ל-Telegram:
    - מדווח activity לכל הודעה נכנסת
    - פקודות /pause ו-/resume לשליטה בניטור
    """
    global running
    offset = None
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"timeout": 50, "offset": offset},
                timeout=60,
            )
            data = resp.json()
            if not data.get("ok"):
                time.sleep(2)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                user = msg.get("from") or {}
                user_id = str(user.get("id")) if user.get("id") else None
                text = (msg.get("text") or "").strip()

                # דיווח פעילות על כל הודעה נכנסת
                if reporter and user_id:
                    try:
                        reporter.report_activity(user_id)
                    except Exception as e:
                        print(f"❗ reporter.report_activity error: {e}")

                if text == "/pause":
                    running = False
                    send("⏸️ Monitoring paused", chat_id=chat_id, user_id=user_id)
                elif text == "/resume":
                    running = True
                    send("▶️ Monitoring resumed", chat_id=chat_id, user_id=user_id)
                elif text == "/status":
                    send(("✅ Responding" if last_status else "❌ Not responding")
                         if last_status is not None else "ℹ️ No checks yet",
                         chat_id=chat_id, user_id=user_id)
        except Exception as e:
            print(f"❗ polling error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    # מריצים ניטור + קליטת פקודות במקביל (Worker, בלי webhook)
    threading.Thread(target=monitor_loop, daemon=True).start()
    polling_loop()
