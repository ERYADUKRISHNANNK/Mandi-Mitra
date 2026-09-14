"""Trust layer — structured farmer feedback and grievance lifecycle."""

import secrets

from .db import execute, now_iso, query, query_one

CATEGORIES = ["EXCESS_WAIT", "SLOT_ISSUE", "TOKEN_ISSUE", "QUALITY_DISPUTE", "WEIGHING_ISSUE",
              "PAYMENT_DELAY", "STAFF_ISSUE", "TECHNICAL", "OTHER"]
RATING_KEYS = ["waiting", "staff", "queue_mgmt", "info", "payment", "facilities", "overall"]


def submit_feedback(token: str, phone: str, mandi_id: str, ratings: dict, comment: str = "") -> dict:
    clean = {k: max(1, min(5, int(ratings.get(k, 3)))) for k in RATING_KEYS}
    execute(
        """
        INSERT INTO feedback (token, phone, mandi_id, waiting, staff, queue_mgmt, info, payment,
                              facilities, overall, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (token, phone, mandi_id, clean["waiting"], clean["staff"], clean["queue_mgmt"],
         clean["info"], clean["payment"], clean["facilities"], clean["overall"],
         comment[:500], now_iso()),
    )
    return {"ok": True, "recorded": clean}


def file_grievance(token: str | None, phone: str, mandi_id: str, category: str, description: str) -> dict:
    if category not in CATEGORIES:
        category = "OTHER"
    gid = f"MM-GRV-{secrets.randbelow(900000) + 100000}"
    execute(
        """
        INSERT INTO grievances (grievance_id, token, phone, mandi_id, category, description, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'SUBMITTED', ?, ?)
        """,
        (gid, token, phone, mandi_id, category, description[:500], now_iso(), now_iso()),
    )
    return {"grievance_id": gid, "status": "SUBMITTED",
            "timeline": ["Submitted", "Assigned", "Under Review", "Action Taken", "Resolved"]}


def track_grievance(grievance_id: str) -> dict | None:
    row = query_one("SELECT * FROM grievances WHERE grievance_id = ?", (grievance_id,))
    if not row:
        return None
    d = dict(row)
    idx = ["SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "ACTION_TAKEN", "RESOLVED"].index(d["status"])
    d["stage_index"] = idx
    return d


def my_grievances(phone: str) -> list[dict]:
    rows = query("SELECT * FROM grievances WHERE phone = ? ORDER BY id DESC LIMIT 20", (phone,))
    out = []
    for r in rows:
        d = dict(r)
        d["stage_index"] = ["SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "ACTION_TAKEN", "RESOLVED"].index(d["status"])
        out.append(d)
    return out


def list_open(mandi_id: str | None = None) -> list[dict]:
    if mandi_id:
        return [dict(r) for r in query(
            "SELECT * FROM grievances WHERE mandi_id = ? AND status != 'RESOLVED' ORDER BY id DESC LIMIT 50",
            (mandi_id,))]
    return [dict(r) for r in query(
        "SELECT * FROM grievances WHERE status != 'RESOLVED' ORDER BY id DESC LIMIT 50")]


def update_status(grievance_id: str, status: str, actor: str, note: str = "") -> dict | None:
    if status not in ("SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "ACTION_TAKEN", "RESOLVED"):
        return None
    execute("UPDATE grievances SET status = ?, resolution = COALESCE(NULLIF(?, ''), resolution), updated_at = ? WHERE grievance_id = ?",
            (status, note, now_iso(), grievance_id))
    return track_grievance(grievance_id)
