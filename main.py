import os
import time
import threading
from collections import deque
import requests
from activity_reporter import create_reporter
from status_watcher import start_status_watcher  # watcher לרסס

# ========= ENV =========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MONGODB_URI = os.getenv("MONGODB_URI")
SERVICE_ID = os.getenv("SERVICE_ID", "srv-unknown")
SERVICE_NAME = os.getenv("SERVICE_NAME", "Cursor-Check")
SUSPENSION_USER_ID = os.getenv("SUSPENSION_USER_ID")  # user id מספרי שלך

# פרמטרים לניטור
SAMPLE_INTERVAL_SEC = int(os.getenv("SAMPLE_INTERVAL_SEC", "60"))
BACK_SUCC_MIN      = int(os.getenv("BACK_SUCC_MIN", "6"))
BACK_WINDOW_SEC    = int(os.getenv("BACK_WINDOW_SEC", "600"))
DOWN_FAILS_MIN     = int(os.getenv("DOWN_FAILS_MIN", "3"))

# ======== Status feed watcher (ENV) ========
STATUS_FEED_URL    = os.getenv("STATUS_FEED_URL", "").strip()      # למשל: https://status.cursor.com/history.atom
STATUS_POLL_SEC    = int(os.getenv("STATUS_POLL_SEC", "180"))
STATUS_STATE_PATH  = os.getenv("STATUS_STATE_PATH", "/tmp/status_feed_state.json")

last_status = None
running = True  # נשלט ע״י /pause ו-/resume

# ========= Reporter init =========
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


def send(text: str, chat_id: str | None = None, user_id: str | None = None) -> None:
    """שליחת הודעה לטלגרם + דיווח activity (best-effort)."""
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
    """בודק שה-API של Cursor מחזיר 200 ויש גוף תשובה."""
    try:
        r = requests.post(
            "https://api2.cursor.sh/aiserver.v1.ChatService/StreamUnifiedChatWithTools",
            json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
            timeout=12,
        )
        if r.status_code != 200:
            return False
        return len((r.text or "")) > 5
    except Exception:
        return False


def check_site_ok() -> bool:
    """בודק שהאתר הראשי מחזיר 200 (מרוכך כדי להימנע מ-False DOWN)."""
    try:
        r = requests.get("https://cursor.sh", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def monitor_loop() -> None:
    """
    'עלה' = גם ה-AI וגם האתר OK (AND), וגם:
      - רצף של BACK_SUCC_MIN הצלחות
      - לפחות BACK_WINDOW_SEC שניות יציבות.
    'נפל' = אחרי DOWN_FAILS_MIN כשלונות רצופים.
    """
    global last_status, running
    send("🤖 cursor-monitor started", user_id="monitor")

    ok_streak = 0
    fail_streak = 0
    first_ok_ts: float | None = None

    while True:
        if running:
            ai_ok = check_cursor_ai()
            web_ok = check_site_ok()
            ok_both = ai_ok and web_ok
            now = time.time()

            if ok_both:
                if ok_streak == 0:
                    first_ok_ts = now
                ok_streak += 1
                fail_streak = 0
            else:
                ok_streak = 0
                first_ok_ts = None
                fail_streak += 1

            # ❌ נפל: רצף כשלונות
            if last_status is not False and fail_streak >= DOWN_FAILS_MIN:
                send(f"❌ Cursor down ({DOWN_FAILS_MIN}/{DOWN_FAILS_MIN} fails)", user_id="monitor")
                last_status = False

            # ✅ חזר: רצף הצלחות + חלון זמן
            if (
                last_status is not True
                and ok_streak >= BACK_SUCC_MIN
                and first_ok_ts is not None
                and (now - first_ok_ts) >= BACK_WINDOW_SEC
            ):
                mins = BACK_WINDOW_SEC // 60
                send(
                    f"✅ Cursor back ({ok_streak}/{BACK_SUCC_MIN} over ≥{mins}m, AND check)",
                    user_id="monitor",
                )
                last_status = True

        time.sleep(SAMPLE_INTERVAL_SEC)


def polling_loop() -> None:
    """פקודות טלגרם: /pause /resume /status /now /last"""
    global running
    offset = None

    # מנקה webhook כדי ש-getUpdates יעבוד
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
                # 🔑 מוודא שהודעה לא תחזור שוב:
                offset = upd["update_id"] + 1

                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                user = msg.get("from") or {}
                user_id = str(user.get("id")) if user.get("id") else None
                text = (msg.get("text") or "").strip()

                # דיווח פעילות לכל הודעה נכנסת (אם יש reporter)
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
                        send(
                            "✅ Responding" if last_status else "❌ Not responding",
                            chat_id=chat_id,
                            user_id=user_id,
                        )

                elif text == "/now":
                    ai_ok = check_cursor_ai()
                    web_ok = check_site_ok()
                    both = ai_ok and web_ok
                    msg_now = (
                        "🔎 Now check\n"
                        f"• AI:   {'OK' if ai_ok else 'DOWN'}\n"
                        f"• Site: {'OK' if web_ok else 'DOWN'}\n"
                        f"• AND:  {'OK' if both else 'DOWN'}"
                    )
                    send(msg_now, chat_id=chat_id, user_id=user_id)

                elif text == "/last":
                    try:
                        # נשתמש בפונקציות מהצופה כדי להביא ולפרמט
                        from status_watcher import _fetch_feed, _format_msg
                        feed = STATUS_FEED_URL or ""
                        if not feed:
                            send("📡 אין STATUS_FEED_URL מוגדר", chat_id=chat_id, user_id=user_id)
                        else:
                            items = _fetch_feed(feed)
                            if not items:
                                send("📡 הפיד ריק כרגע", chat_id=chat_id, user_id=user_id)
                            else:
                                items.sort(key=lambda x: x.get("updated_ts", 0.0))
                                latest = items[-1]
                                msg = _format_msg(latest)
                                send("📡 הפריט האחרון מהפיד:\n" + msg, chat_id=chat_id, user_id=user_id)
                    except Exception as e:
                        send(f"❗ שגיאה ב-/last: {e}", chat_id=chat_id, user_id=user_id)

        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    # דיווח פתיחה כדי שבוט ההשעיה יזהה מיידית
    if reporter and SUSPENSION_USER_ID:
        try:
            reporter.report_activity(SUSPENSION_USER_ID)
        except Exception:
            pass

    # 🔭 מפעילים צופה סטטוס רשמי (אם הוגדר feed)
    def _send_status_to_telegram(text: str) -> None:
        send(f"📡 Status feed\n{text}", user_id="status-feed")

    start_status_watcher(
        STATUS_FEED_URL or None,
        STATUS_POLL_SEC,
        STATUS_STATE_PATH,
        _send_status_to_telegram,
    )

    # מריץ ניטור + קליטת פקודות במקביל
    threading.Thread(target=monitor_loop, daemon=True).start()
    print("👂 polling_loop started", flush=True)
    polling_loop()
