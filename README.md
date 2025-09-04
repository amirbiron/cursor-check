# Cursor-Check

ניטור ל-**Cursor** עם מניעת false-positives:
- **AND**: גם ה-AI API וגם האתר חייבים להיות OK.
- “חזר” רק אחרי **רצף הצלחות** וגם **חלון זמן יציב**.
- “נפל” רק אחרי **רצף כשלונות**.
- התראות לטלגרם + אינטגרציה עם **בוט ההשעיה** (activity reporter).

## Run
Render Worker → Start: `python main.py`

## Required ENV
| Key | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `CHAT_ID` | Chat ID לנוטיפיקציות |
| `MONGODB_URI` | חיבור ל-MongoDB (activity) |
| `SERVICE_ID` | מזהה שירות מ-Render |
| `SERVICE_NAME` | שם ידידותי לשירות |
| `SUSPENSION_USER_ID` | user id שלך (לזיהוי מיידי על Boot) |

## Tuning (optional)
| Key | Default | Meaning |
|-----|---------|---------|
| `SAMPLE_INTERVAL_SEC` | `60` | מרווח דגימה (שניות) |
| `BACK_SUCC_MIN` | `6` | מינימום הצלחות רצופות ל"חזר" |
| `BACK_WINDOW_SEC` | `600` | חלון יציבות ל"חזר" (שניות) |
| `DOWN_FAILS_MIN` | `3` | מינימום כשלונות רצופים ל"נפל" |

## Commands
- `/status` – מצב נוכחי
- `/pause` – השהיית ניטור
- `/resume` – חידוש ניטור
