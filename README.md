# Cursor-Check

שירות ניטור ל-**Cursor**: בודק את API ה-AI והאתר, ומדווח טלגרם רק על שינוי מצב.
כולל תמיכה בבוט ההשעיה (Activity Reporter).

## הרצה
Runtime: Python • Start: `python main.py`

## ENV חובה
| Key | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | טוקן מה-BotFather |
| `CHAT_ID` | יעד לשליחת נוטיפיקציות |
| `MONGODB_URI` | חיבור ל-activity (בוט ההשעיה) |
| `SERVICE_ID` | מזהה השירות מ-Render |
| `SERVICE_NAME` | שם ידידותי לשירות |
| `SUSPENSION_USER_ID` | user id שלך (לזיהוי מיידי בהפעלה) |

## פקודות טלגרם
- `/status` – סטטוס נוכחי
- `/pause` – השהיית הניטור
- `/resume` – חידוש הניטור

---
_Last updated: 2025-09-04T00:44:25Z_
