import os
import time
import threading
import requests
from activity_reporter import create_reporter

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MONGODB_URI = os.getenv("MONGODB_URI")
SERVICE_ID = os.getenv("SERVICE_ID", "srv-unknown")
SERVICE_NAME = os.getenv("SERVICE_NAME", "Cursor-Check")
SUSPENSION_USER_ID = os.getenv("SUSPENSION_USER_ID")

reporter = None
if MONGODB_URI:
    try:
        reporter = create_reporter(
            mongodb_uri=MONGODB_URI, service_id=SERVICE_ID, service_name=SERVICE_NAME
        )
        print("✅ activity_reporter initialized", flush=True)
    except Exception as e:
        print(f"❗ activity_reporter init failed: {e}", flush=True)
else:
    print("ℹ️ MONGODB_URI not set – activity reporting disabled", flush=True)

last_status = None
running = True

def send(text: str, chat_id: str | None = None, user_id: str | None = None) -> None:
    target = chat_id or CHAT_ID
    if not TOKEN or not target:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": target, "text": text},
            timeout=10,
        )
        if reporter:
            try:
                reporter.report_activity(user_id or SUSPENSION_USER_ID or "system")
            except Exception:
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

def check_site_ok() -> bool:
    try:
        r = requests.get("https://cursor.sh", timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def monitor_loop() -> None:
    global last_status, running
    send("🤖 cursor-monitor started", user_id="monitor")
    ok_streak = 0
    fail_streak = 0
    while True:
        if running:
            status = check_cursor_ai() or check_site_ok()
            if status:
                ok_streak += 1
                fail_streak = 0
            else:
                fail_streak += 1
                ok_streak = 0
            if last_status is not True and ok_streak >= 2:
                send("✅ Cursor looks back (2/2 checks)", user_id="monitor")
                last_status = True
            elif last_status is not False and fail_streak >= 2:
                send("❌ Cursor looks down (2/2 checks)", user_id="monitor")
                last_status = False
        time.sleep(60)

def polling_loop() -> None:
    global running
    offset = None
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": ""},
            timeout=10,
        )
    except Exception:
        pass
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
                if reporter:
                    try:
                        reporter.report_activity(user_id or (str(chat_id) if chat_id else None))
                    except Exception:
                        pass
                if text == "/pause":
                    running = False
                    send("⏸️ Monitoring paused", chat_id=chat_id, user_id=user_id)
                elif text == "/resume":
                    running = True
                    send("▶️ Monitoring resumed", chat_id=chat_id, user_id=user_id)
                elif text == "/status":
                    if last_status is None:
                        send("ℹ️ No checks yet", chat_id=chat_id, user_id=user_id)
                    else:
                        send("✅ Responding" if last_status else "❌ Not responding",
                             chat_id=chat_id, user_id=user_id)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    if reporter and SUSPENSION_USER_ID:
        try:
            reporter.report_activity(SUSPENSION_USER_ID)
        except Exception:
            pass
    import threading as _t
    _t.Thread(target=monitor_loop, daemon=True).start()
    print("👂 polling_loop started", flush=True)
    polling_loop()
