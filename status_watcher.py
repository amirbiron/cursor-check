import os
import time
import json
import re
from typing import Callable, Dict, Any, List, Optional
import requests
import xml.etree.ElementTree as ET


# ---- הגדרות מ־ENV (אפשר גם מהקובץ הקורא) ----
DEFAULT_FEED_URL = os.getenv("STATUS_FEED_URL", "").strip()  # לדוגמה: https://status.cursor.com/history.atom או .rss
POLL_SEC = int(os.getenv("STATUS_POLL_SEC", "180"))          # כל כמה שניות לבדוק פיד (דיפולט: 3 דק')
STATE_PATH = os.getenv("STATUS_STATE_PATH", "/tmp/status_feed_state.json")


def _norm_text(s: Optional[str]) -> str:
    return (s or "").strip()


def _get_text(elem: Optional[ET.Element]) -> str:
    return _norm_text(elem.text if elem is not None else "")


def _parse_atom(root: ET.Element) -> List[Dict[str, Any]]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall(".//a:entry", ns):
        entry_id = _get_text(entry.find("a:id", ns))
        title = _get_text(entry.find("a:title", ns))
        updated = _get_text(entry.find("a:updated", ns)) or _get_text(entry.find("a:published", ns))
        link = ""
        link_el = entry.find("a:link", ns)
        if link_el is not None:
            link = link_el.get("href", "")
        summary = _get_text(entry.find("a:summary", ns))
        # לפעמים יש תוכן ולא סיכום
        content_el = entry.find("a:content", ns)
        content = _get_text(content_el) if content_el is not None else ""
        items.append(
            {
                "id": entry_id or f"{title}|{updated}",
                "title": title,
                "updated": updated,
                "link": link,
                "summary": summary or content,
            }
        )
    return items


def _parse_rss(root: ET.Element) -> List[Dict[str, Any]]:
    items = []
    for item in root.findall(".//item"):
        guid_el = item.find("guid")
        guid = _get_text(guid_el)
        title = _get_text(item.find("title"))
        pub = _get_text(item.find("pubDate")) or _get_text(item.find("date"))
        link = _get_text(item.find("link"))
        desc = _get_text(item.find("description"))
        items.append(
            {
                "id": guid or f"{title}|{pub}",
                "title": title,
                "updated": pub,
                "link": link,
                "summary": desc,
            }
        )
    return items


def _load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_ids": []}  # נשמור עד 50 אחרונים


def _save_state(path: str, state: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def _classify(title: str, body: str) -> str:
    """מנסה לשים אייקון לפי מילים נפוצות."""
    t = f"{title} {body}".lower()
    if re.search(r"\b(resolved|fixed|restored|monitoring)\b", t):
        return "✅ Resolved"
    if re.search(r"\b(investigating|degraded|degradation|partial outage|incident)\b", t):
        return "🚨 Incident"
    if re.search(r"\b(identified|mitigating|recovering)\b", t):
        return "🛠️ Mitigating"
    return "🔔 Update"


def _format_msg(item: Dict[str, Any]) -> str:
    title = item.get("title") or ""
    when = item.get("updated") or ""
    link = item.get("link") or ""
    summary = item.get("summary") or ""
    label = _classify(title, summary)
    # חיתוך תקציר למובייל
    short = summary.strip().replace("\n", " ")
    if len(short) > 280:
        short = short[:277] + "..."
    parts = [
        f"{label}: {title}",
        f"🕒 {when}" if when else "",
        f"🔗 {link}" if link else "",
        f"— {short}" if short else "",
    ]
    return "\n".join([p for p in parts if p])


def _fetch_feed(feed_url: str) -> List[Dict[str, Any]]:
    r = requests.get(feed_url, timeout=12)
    r.raise_for_status()
    # ננסה לזהות אטום/‏RSS לפי root tag
    root = ET.fromstring(r.text)
    tag = root.tag.lower()
    if "feed" in tag:   # atom
        return _parse_atom(root)
    return _parse_rss(root)  # rss


def watch_once(feed_url: str, state: Dict[str, Any], on_event: Callable[[str], None]) -> Dict[str, Any]:
    last_ids: List[str] = list(state.get("last_ids", []))
    items = _fetch_feed(feed_url)
    # newest first אם אפשר (לפי סדר הופעה)
    new_msgs = []
    for it in items:
        _id = it.get("id") or ""
        if not _id:
            continue
        if _id in last_ids:
            continue
        new_msgs.append(_format_msg(it))
        last_ids.append(_id)

    # גבול לרשימת ה־ids
    if len(last_ids) > 50:
        last_ids = last_ids[-50:]

    # שליחת הודעות בסדר מהישן לחדש כדי לא לבלגן כרונולוגיה
    for msg in reversed(new_msgs):
        try:
            on_event(msg)
        except Exception:
            pass

    state["last_ids"] = last_ids
    return state


def start_status_watcher(
    feed_url: Optional[str],
    poll_sec: Optional[int],
    state_path: Optional[str],
    send_fn: Callable[[str], None],
) -> None:
    """
    מריץ לולאה בחוט נפרד: מושך פיד סטטוס כל poll_sec שניות, שולח עדכונים חדשים.
    """
    url = (feed_url or DEFAULT_FEED_URL).strip()
    if not url:
        print("ℹ️ STATUS_FEED_URL not set – skipping status watcher", flush=True)
        return

    interval = int(poll_sec or POLL_SEC)
    path = state_path or STATE_PATH

    def _run():
        st = _load_state(path)
        print(f"🔭 status watcher started (feed={url}, every {interval}s)", flush=True)
        while True:
            try:
                st = watch_once(url, st, send_fn)
                _save_state(path, st)
            except Exception as e:
                print(f"❗ status watcher error: {e}", flush=True)
            time.sleep(interval)

    import threading as _t

    _t.Thread(target=_run, daemon=True).start()
