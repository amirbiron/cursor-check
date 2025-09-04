# status_watcher.py
# Watch Cursor (or any Statuspage-style) RSS/Atom feed and push concise Hebrew updates.

import os
import time
import json
import re
from typing import Callable, Dict, Any, List, Optional
import requests
import xml.etree.ElementTree as ET

# ===== ENV & Defaults =====
DEFAULT_FEED_URL = os.getenv("STATUS_FEED_URL", "").strip()
POLL_SEC         = int(os.getenv("STATUS_POLL_SEC", "180"))
STATE_PATH       = os.getenv("STATUS_STATE_PATH", "/tmp/status_feed_state.json")

ONLY_INCIDENTLIKE    = os.getenv("STATUS_ONLY_INCIDENTS", "true").lower() == "true"
SKIP_ANALYTICS       = os.getenv("STATUS_SKIP_ANALYTICS", "true").lower() == "true"
MAX_PER_POLL         = int(os.getenv("STATUS_MAX_PER_POLL", "2"))
COOLDOWN_SEC         = int(os.getenv("STATUS_COOLDOWN_SEC", "900"))
BOOT_IGNORE_HISTORY  = os.getenv("STATUS_BOOT_IGNORE_HISTORY", "true").lower() == "true"
SEND_LAST_ON_BOOT    = os.getenv("STATUS_SEND_LAST_ON_BOOT", "true").lower() == "true"

# תצוגה בעברית – קצר וברור
STATUS_HEBREW        = os.getenv("STATUS_HEBREW", "true").lower() == "true"
STATUS_TZ            = os.getenv("STATUS_TZ", "Asia/Jerusalem")
# לכל מקרה שתרצה כן לכלול תקציר טקסט חופשי:
STATUS_INCLUDE_SUMMARY = os.getenv("STATUS_INCLUDE_SUMMARY", "false").lower() == "true"

BOOT_TS = time.time()

# ===== Utils =====
_HTML_TAG_RE = re.compile(r"<[^>]+>")
WS_RE        = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _HTML_TAG_RE.sub(" ", s or "")
    return WS_RE.sub(" ", s).strip()


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _get_text(elem: Optional[ET.Element]) -> str:
    return _norm(elem.text if elem is not None else "")


def _parse_time_guess(s: str) -> float:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        try:
            from datetime import datetime
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return time.time()


def _fmt_local(ts: float) -> str:
    try:
        from zoneinfo import ZoneInfo
        import datetime as _dt
        dt = _dt.datetime.fromtimestamp(ts, ZoneInfo(STATUS_TZ))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _classify(title: str, body: str) -> str:
    t = f"{title} {body}".lower()
    if re.search(r"\b(resolved|fixed|restored)\b", t):
        return "resolved"
    if re.search(r"\b(monitoring|observing)\b", t):
        return "monitoring"
    if re.search(r"\b(investigating|degraded|degradation|partial outage|incident|outage)\b", t):
        return "incident"
    if re.search(r"\b(identified|mitigating|recovering|update)\b", t):
        return "update"
    return "other"


def _is_analytics(title: str, body: str) -> bool:
    t = f"{title} {body}".lower()
    return "analytic" in t  # analytics / analytic


# ===== Feed parsing =====
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
            link = (link_el.get("href") or "").strip()
        summary = _get_text(entry.find("a:summary", ns))
        content_el = entry.find("a:content", ns)
        content = _get_text(content_el) if content_el is not None else ""
        body = _strip_html(summary or content)
        items.append(
            {
                "id": entry_id or f"{title}|{updated}",
                "title": title,
                "updated": updated,
                "updated_ts": _parse_time_guess(updated),
                "link": link,
                "summary": body,
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
        desc = _strip_html(_get_text(item.find("description")))
        items.append(
            {
                "id": guid or f"{title}|{pub}",
                "title": title,
                "updated": pub,
                "updated_ts": _parse_time_guess(pub),
                "link": link,
                "summary": desc,
            }
        )
    return items


def _fetch_feed(feed_url: str) -> List[Dict[str, Any]]:
    r = requests.get(feed_url, timeout=12)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    tag = root.tag.lower()
    if "feed" in tag:  # Atom
        return _parse_atom(root)
    return _parse_rss(root)  # RSS


# ===== State =====
def _load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_ids": [], "last_sent_ts": 0.0, "boot_sent": False}


def _save_state(path: str, state: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


# ===== Formatting (Hebrew concise) =====
def _format_msg(item: Dict[str, Any]) -> str:
    title = item.get("title") or ""
    when = item.get("updated") or ""
    when_ts = float(item.get("updated_ts") or _parse_time_guess(when))
    link = item.get("link") or ""
    summary = item.get("summary") or ""

    typ = _classify(title, summary)

    if STATUS_HEBREW:
        # תוויות קצרות בעברית
        label_map = {
            "resolved":   "✅ התקלה נפתרה",
            "monitoring": "🟡 במעקב",
            "incident":   "🔴 נחקרת תקלה",
            "update":     "🔔 עדכון",
            "other":      "🔔 עדכון",
        }
        label = label_map.get(typ, "🔔 עדכון")
        local = _fmt_local(when_ts)

        parts = [
            "📡 עדכון סטטוס:",
            f"{label}: {title}".strip(),
            f"🕒 {local} ({STATUS_TZ})",
            f"🔗 {link}" if link else "",
        ]
        if STATUS_INCLUDE_SUMMARY and summary:
            # אופציונלי – אם תרצה גם שורה קצרה מתוכן ההודעה
            short = summary.strip()
            if len(short) > 240:
                short = short[:237] + "..."
            parts.append(f"— {short}")
        return "\n".join([p for p in parts if p])

    # ברירת מחדל: אנגלית קצרה
    icon_map = {
        "resolved": "✅ Resolved",
        "monitoring": "🟡 Monitoring",
        "incident": "🔴 Incident",
        "update": "🔔 Update",
    }
    icon = icon_map.get(typ, "🔔 Update")
    parts = [
        "📡 Status update:",
        f"{icon}: {title}",
        f"🕒 {when}" if when else "",
        f"🔗 {link}" if link else "",
    ]
    if STATUS_INCLUDE_SUMMARY and summary:
        short = summary.strip()
        if len(short) > 240:
            short = short[:237] + "..."
        parts.append(f"— {short}")
    return "\n".join([p for p in parts if p])


def _should_send(item: Dict[str, Any]) -> bool:
    title = item.get("title") or ""
    body = item.get("summary") or ""
    typ = _classify(title, body)
    if ONLY_INCIDENTLIKE and typ not in ("incident", "resolved", "monitoring"):
        return False
    if SKIP_ANALYTICS and _is_analytics(title, body):
        return False
    return True


def _pick_latest_allowed(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    allowed = [it for it in items if _should_send(it)]
    if not allowed:
        return None
    allowed.sort(key=lambda x: x.get("updated_ts", 0.0))
    return allowed[-1]


# ===== Core =====
def watch_once(feed_url: str, state: Dict[str, Any], on_event: Callable[[str], None]) -> Dict[str, Any]:
    last_ids: List[str] = list(state.get("last_ids", []))
    last_sent_ts: float = float(state.get("last_sent_ts", 0.0))
    boot_sent: bool = bool(state.get("boot_sent", False))
    now = time.time()

    items = _fetch_feed(feed_url)

    # שליחה חד-פעמית על Boot (פריט אחרון שעובר מסננים; אם אין – לא שולח)
    if SEND_LAST_ON_BOOT and not boot_sent:
        latest = _pick_latest_allowed(items)
        if latest:
            try:
                on_event(_format_msg(latest))
            except Exception:
                pass
        # מסמנים את כולם כנצפו כדי שלא להציף אחר-כך
        for it in items:
            _id = it.get("id")
            if _id and _id not in last_ids:
                last_ids.append(_id)
        state["last_sent_ts"] = now  # לא מגביל ע"י cooldown על הודעת boot
        state["boot_sent"] = True
        state["last_ids"] = last_ids
        return state

    fresh: List[Dict[str, Any]] = []
    for it in items:
        it_id = it.get("id") or ""
        if not it_id:
            continue
        if it_id in last_ids:
            continue
        # מתעלמים מהיסטוריה לפני העלייה אם ביקשת
        if BOOT_IGNORE_HISTORY and it.get("updated_ts", now) < BOOT_TS:
            last_ids.append(it_id)
            continue
        if not _should_send(it):
            last_ids.append(it_id)
            continue
        fresh.append(it)

    fresh.sort(key=lambda x: x.get("updated_ts", now))

    sent = 0
    for it in fresh:
        if sent >= MAX_PER_POLL:
            break
        if COOLDOWN_SEC > 0 and (now - last_sent_ts) < COOLDOWN_SEC:
            break
        try:
            on_event(_format_msg(it))
            last_sent_ts = now
            sent += 1
        except Exception:
            pass
        finally:
            _id = it.get("id")
            if _id:
                last_ids.append(_id)

    if len(last_ids) > 200:
        last_ids = last_ids[-200:]

    state["last_ids"] = last_ids
    state["last_sent_ts"] = last_sent_ts
    return state


def start_status_watcher(
    feed_url: Optional[str],
    poll_sec: Optional[int],
    state_path: Optional[str],
    send_fn: Callable[[str], None],
) -> None:
    url = (feed_url or DEFAULT_FEED_URL).strip()
    if not url:
        print("ℹ️ STATUS_FEED_URL not set – skipping status watcher", flush=True)
        return

    interval = int(poll_sec or POLL_SEC)
    path = state_path or STATE_PATH

    def _run():
        st = _load_state(path)
        print(
            f"🔭 status watcher started feed={url}, poll={interval}s, "
            f"only_incidents={ONLY_INCIDENTLIKE}, skip_analytics={SKIP_ANALYTICS}, "
            f"cooldown={COOLDOWN_SEC}s, max_per_poll={MAX_PER_POLL}, "
            f"boot_ignore_history={BOOT_IGNORE_HISTORY}, send_last_on_boot={SEND_LAST_ON_BOOT}, "
            f"hebrew={STATUS_HEBREW}, include_summary={STATUS_INCLUDE_SUMMARY}",
            flush=True,
        )
        while True:
            try:
                st = watch_once(url, st, send_fn)
                _save_state(path, st)
            except Exception as e:
                print(f"❗ status watcher error: {e}", flush=True)
            time.sleep(interval)

    import threading as _t
    _t.Thread(target=_run, daemon=True).start()
