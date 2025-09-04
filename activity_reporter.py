from datetime import datetime
from typing import Protocol

from pymongo import MongoClient


class _Reporter(Protocol):
    def report_activity(self, user_id: str) -> None: ...  # noqa: E701


def create_reporter(mongodb_uri: str, service_id: str, service_name: str) -> _Reporter:
    """Return a tiny reporter object that writes activity rows to MongoDB."""
    client = MongoClient(mongodb_uri)
    db = client["suspension_bot"]
    col = db["activity"]

    def report_activity(user_id: str) -> None:
        col.insert_one(
            {
                "service_id": service_id,
                "service_name": service_name,
                "user_id": user_id,
                "ts": datetime.utcnow(),
            }
        )

    return type("Reporter", (), {"report_activity": report_activity})()
