from pymongo import MongoClient
from datetime import datetime, timezone

class SimpleActivityReporter:
    def __init__(self, mongodb_uri, service_id, service_name=None):
        try:
            self.client = MongoClient(mongodb_uri)
            self.db = self.client["render_bot_monitor"]
            self.service_id = service_id
            self.service_name = service_name or service_id
            self.connected = True
        except Exception:
            self.connected = False
            print("⚠️ לא ניתן להתחבר למונגו - פעילות לא תירשם")

    def _now(self):
        return datetime.now(timezone.utc)

    def report_activity(self, user_id):
        """דיווח פעילות משתמש/אירוע"""
        if not self.connected:
            return
        now = self._now()
        try:
            # --- טבלת אינטראקציות משתמשים (כמו קודם) ---
            self.db.user_interactions.update_one(
                {"service_id": self.service_id, "user_id": user_id},
                {
                    "$set": {"last_interaction": now},
                    "$inc": {"interaction_count": 1},
                    "$setOnInsert": {"created_at": now, "service_name": self.service_name},
                },
                upsert=True,
            )

            # --- טבלת פעילות שירות (תאימות רחבה) ---
            # 1) מזהה גם ב-_id וגם בשדה service_id
            self.db.service_activity.update_one(
                {"_id": self.service_id},
                {
                    "$set": {
                        "service_id": self.service_id,         # תאימות
                        "service_name": self.service_name,
                        "updated_at": now,
                        "status": "active",
                        # שדות עם שמות שונים שבוטים נוהגים לחפש:
                        "last_user_activity": now,             # הסכמה שלך
                        "last_activity": now,                  # סכמה חלופית נפוצה
                        "last_seen": now,                      # סכמה חלופית נוספת
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        "total_users": 0,
                        "suspend_count": 0,
                    },
                },
                upsert=True,
            )

        except Exception:
            # אל תפיל את הבוט על דיווח
            pass

    def report_service_heartbeat(self):
        """Heartbeat בלי לגעת בטבלת user_interactions"""
        if not self.connected:
            return
        now = self._now()
        try:
            self.db.service_activity.update_one(
                {"_id": self.service_id},
                {
                    "$set": {
                        "service_id": self.service_id,     # תאימות
                        "service_name": self.service_name,
                        "updated_at": now,
                        "status": "active",
                        # שלושה שמות שדה מקבילים כדי לתפוס כל בוט השעיה
                        "last_user_activity": now,
                        "last_activity": now,
                        "last_seen": now,
                    },
                    "$setOnInsert": {"created_at": now, "total_users": 0, "suspend_count": 0},
                },
                upsert=True,
            )
        except Exception:
            pass


def create_reporter(mongodb_uri, service_id, service_name=None):
    return SimpleActivityReporter(mongodb_uri, service_id, service_name)
