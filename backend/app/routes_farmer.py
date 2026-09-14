"""Farmer-facing endpoints: registration, booking, live status, receipts, IVR."""

import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import anomaly, congestion, receipts
from .audit import log_event
from .db import execute, now_iso, query, query_one, today_str
from .i18n import SUPPORTED_LANGS, render
from .notify import recent as recent_notifications, send_sms, send_voice
from .pricing import procurement_amount
from .queue_engine import get_snapshot, get_ticket_public, recompute_mandi
from .security import issue_otp, verify_otp
from .slots import recommend_slots

router = APIRouter(prefix="/api/farmer", tags=["farmer"])


class RegisterIn(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    name: str = ""
    lang: str = "ml"


class OtpRequestIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


class BookIn(BaseModel):
    mandi_id: str
    phone: str
    farmer_name: str
    crop: str
    quantity_kg: float = Field(gt=0)
    slot_date: str | None = None
    slot_time: str
    lang: str = "ml"
    priority_flag: str | None = None


class IvrIn(BaseModel):
    phone: str | None = None
    token: str | None = None
    lang: str = "ml"


class SelfCheckInIn(BaseModel):
    token: str
    lat: float
    lng: float


class DisputeIn(BaseModel):
    token: str
    category: str = "GENERAL"  # WEIGHT | QUALITY | PAYMENT | GENERAL
    note: str = ""


class AckIn(BaseModel):
    token: str


class BookIn2(BaseModel):
    """Extended booking fields for priority requests."""

    priority_flag: str | None = None  # ELDERLY | DISABLED | SMALL_HOLDER


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (0.5 - math.cos((lng2 - lng1) * p) / 2))
    return 12742 * math.asin(math.sqrt(a))


def _mm_id(phone: str) -> str:
    return "MM-" + hashlib.sha256(phone.encode()).hexdigest()[:6].upper()


def next_token(mandi_id: str) -> str:
    """Collision-safe token minting (retry on the rare race)."""
    import sqlite3 as _sq
    for _ in range(5):
        try:
            max_id = query_one("SELECT COALESCE(MAX(id), 0) AS m FROM tickets")["m"]
            candidate = f"MND-{1000 + max_id + 1}"
            if not query_one("SELECT 1 FROM tickets WHERE token = ?", (candidate,)):
                return candidate
        except _sq.Error:
            pass
    return f"MND-{1000 + secrets_rand_int()}"


def secrets_rand_int() -> int:
    import secrets
    return secrets.randbelow(90000) + 10000


def _register_farmer(phone: str, name: str, lang: str) -> dict:
    mm = _mm_id(phone)
    row = query_one("SELECT * FROM farmers WHERE phone = ?", (phone,))
    if row:
        if name or lang:
            execute("UPDATE farmers SET name = COALESCE(NULLIF(?, ''), name), lang = ? WHERE phone = ?",
                    (name, lang, phone))
        return {"phone": phone, "mm_id": row["mm_id"], "name": row["name"], "lang": row["lang"]}
    execute("INSERT INTO farmers (phone, mm_id, name, lang, created_at) VALUES (?, ?, ?, ?, ?)",
            (phone, mm, name, lang, now_iso()))
    return {"phone": phone, "mm_id": mm, "name": name, "lang": lang}


def _trust_score(phone: str) -> dict:
    row = query_one(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status = 'NO_SHOW' THEN 1 ELSE 0 END) AS no_shows
        FROM tickets WHERE phone = ?
        """,
        (phone,),
    )
    total = row["total"] or 0
    completed = row["completed"] or 0
    no_shows = row["no_shows"] or 0
    score = 50 + (completed * 10) - (no_shows * 15) if total else 75
    score = max(0, min(100, score))
    return {"score": score, "bookings": total, "completed": completed, "no_shows": no_shows}


@router.post("/register")
def register(body: RegisterIn):
    if body.lang not in SUPPORTED_LANGS:
        body.lang = "ml"
    farmer = _register_farmer(body.phone, body.name, body.lang)
    log_event(None, "SYSTEM", "FARMER_REGISTERED", {"phone": body.phone, "mm_id": farmer["mm_id"]})
    return {**farmer, "note": "Share your Mandi Mitra ID to check status by SMS or missed call — no login needed."}


@router.post("/otp/request")
def otp_request(body: OtpRequestIn):
    code = issue_otp(body.phone)
    return {"sent": True, "channel": "SMS (simulated gateway)", "simulated_otp": code,
            "note": "Prototype returns the OTP inline; production sends it via the SMS gateway."}


@router.post("/otp/verify")
def otp_verify(body: OtpVerifyIn):
    if verify_otp(body.phone, body.code):
        farmer = _register_farmer(body.phone, "", "ml")
        return {"verified": True, **farmer}
    raise HTTPException(status_code=400, detail="Invalid or expired OTP")


@router.get("/slots")
def slots(mandi_id: str, slot_date: str | None = None, quantity_kg: float = 0):
    return recommend_slots(mandi_id, slot_date, quantity_kg)


@router.post("/book")
def book(body: BookIn):
    if body.lang not in SUPPORTED_LANGS:
        body.lang = "ml"
    mandi = query_one("SELECT * FROM mandis WHERE id = ?", (body.mandi_id,))
    if not mandi:
        raise HTTPException(status_code=404, detail="Unknown mandi")

    slot_date = body.slot_date or today_str()
    if slot_date != today_str() and slot_date < today_str():
        raise HTTPException(status_code=400, detail="Slot date is in the past")

    # Duplicate-booking guard: same phone + mandi + date already active.
    dup = query_one(
        """
        SELECT token FROM tickets WHERE phone = ? AND mandi_id = ? AND slot_date = ?
          AND status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')
        """,
        (body.phone, body.mandi_id, slot_date),
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Active booking already exists: {dup['token']}")

    # Slot capacity guard.
    capacity = recommend_slots(body.mandi_id, slot_date, body.quantity_kg)
    chosen = next((o for o in capacity["options"] if o["slot_time"] == body.slot_time), None)
    if chosen and chosen["headroom"] <= 0:
        raise HTTPException(status_code=409, detail=f"Slot {body.slot_time} is full — pick another recommended slot")

    _register_farmer(body.phone, body.farmer_name, body.lang)

    token = next_token(body.mandi_id)

    priority = 1 if body.priority_flag in ("ELDERLY", "DISABLED", "SMALL_HOLDER") else 0
    execute(
        """
        INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg,
            slot_date, slot_time, lang, status, priority, priority_flag, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SLOT_BOOKED', ?, ?, ?)
        """,
        (token, body.mandi_id, body.phone, body.farmer_name, body.crop, body.quantity_kg,
         slot_date, body.slot_time, body.lang, priority, body.priority_flag, now_iso()),
    )
    ticket = query_one("SELECT * FROM tickets WHERE token = ?", (token,))
    log_event(body.mandi_id, f"FARMER:{body.phone}", "BOOKING_CREATED",
              {"token": token, "slot": f"{slot_date} {body.slot_time}", "crop": body.crop,
               "quantity_kg": body.quantity_kg}, ticket["id"])
    send_sms(body.phone, body.lang, "BOOKING_CONFIRMED",
             {"token": token, "crop": body.crop, "date": slot_date, "time": body.slot_time}, ticket["id"])

    snap = recompute_mandi(body.mandi_id)
    mine = next((q for q in snap["queue"] if q["ticket_id"] == ticket["id"]), None)
    result = get_ticket_public(ticket)
    result["upcoming_queue_length"] = len(snap["queue"])
    if mine:
        result["position"] = mine["position"]
        result["eta_minutes"] = mine["eta_minutes"]
        result["eta_confidence"] = mine["eta_confidence"]
    return result


def _find_ticket(token: str | None, phone: str | None):
    if token:
        return query_one("SELECT * FROM tickets WHERE token = ?", (token,))
    if phone:
        return query_one(
            """
            SELECT * FROM tickets WHERE phone = ? AND status IN
            ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')
            ORDER BY id DESC LIMIT 1
            """,
            (phone,),
        )
    return None


@router.get("/status")
def status(token: str | None = None, phone: str | None = None):
    ticket = _find_ticket(token, phone)
    if not ticket:
        raise HTTPException(status_code=404, detail="No active booking found for that token/phone")
    recompute_mandi(ticket["mandi_id"])
    fresh = query_one("SELECT * FROM tickets WHERE id = ?", (ticket["id"],))
    snap = get_snapshot(ticket["mandi_id"])
    mine = next((q for q in snap["queue"] if q["ticket_id"] == ticket["id"]), None)

    result = get_ticket_public(fresh)
    if mine:
        result.update({"position": mine["position"], "eta_minutes": mine["eta_minutes"],
                       "eta_confidence": mine["eta_confidence"], "queue_group": mine["queue_group"]})
    result["mandi_name"] = query_one("SELECT name FROM mandis WHERE id = ?", (ticket["mandi_id"],))["name"]
    result["trust"] = _trust_score(ticket["phone"])
    result["timeline"] = timeline_events(ticket["id"])
    return result


@router.get("/timeline/{token}")
def timeline(token: str):
    ticket = query_one("SELECT id FROM tickets WHERE token = ?", (token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    return {"token": token, "events": timeline_events(ticket["id"])}


def timeline_events(ticket_id: int) -> list[dict]:
    rows = query(
        "SELECT ts, actor, action, details FROM audit_events WHERE ticket_id = ? ORDER BY id",
        (ticket_id,),
    )
    events = []
    for r in rows:
        try:
            import json as _json
            details = _json.loads(r["details"] or "{}")
        except Exception:
            details = {}
        events.append({"ts": r["ts"], "actor": r["actor"], "action": r["action"], "details": details})
    return events


@router.get("/receipt/{token}")
def receipt(token: str):
    rec = receipts.get_receipt(token)
    if not rec:
        raise HTTPException(status_code=404, detail="No receipt yet — procurement not completed")
    chain = receipts.verify_chain(rec["mandi_id"])
    return {"receipt": rec, "chain_verified": chain["verified"]}


@router.get("/notifications")
def notifications(phone: str):
    rows = query(
        "SELECT channel, template_key, lang, body, simulated, created_at FROM notifications"
        " WHERE phone = ? ORDER BY id DESC LIMIT 25",
        (phone,),
    )
    return {"phone": phone, "count": len(rows), "notifications": [dict(r) for r in rows]}


@router.post("/ivr/call")
def ivr_call(body: IvrIn):
    """Simulated IVR: farmer dials in, system speaks the live status."""
    lang = body.lang if body.lang in SUPPORTED_LANGS else "ml"
    ticket = _find_ticket(body.token, body.phone)
    if not ticket:
        return {"ivr_says": render(lang, "NO_SHOW_REMINDER", {"token": "—"}),
                "error": "No booking found", "lang": lang}

    recompute_mandi(ticket["mandi_id"])
    fresh = query_one("SELECT * FROM tickets WHERE id = ?", (ticket["id"],))
    snap = get_snapshot(ticket["mandi_id"])
    mine = next((q for q in snap["queue"] if q["ticket_id"] == ticket["id"]), None)

    status_key = fresh["status"]
    ctx = {
        "token": fresh["token"],
        "position": (mine["position"] if mine else 0) - 1,
        "eta": int(mine["eta_minutes"] or 0),
        "eta_time": "—",
        "counter": "1",
        "grade": fresh["quality_grade"] or "—",
        "amount": int(fresh["amount"] or 0),
        "crop": fresh["crop"],
        "date": fresh["slot_date"],
        "time": fresh["slot_time"],
    }
    template = {
        "SLOT_BOOKED": "BOOKING_CONFIRMED",
        "ARRIVED": "ARRIVAL_CONFIRMED",
        "WEIGHING": "WEIGHING_STARTED",
        "QUALITY_CHECK": "QUALITY_CHECK",
        "PAYMENT": "PAYMENT_INITIATED" if fresh["payment_status"] != "COMPLETED" else "PAYMENT_RECEIVED",
        "COMPLETED": "PAYMENT_RECEIVED",
        "NO_SHOW": "NO_SHOW_REMINDER",
    }.get(status_key, "ARRIVAL_CONFIRMED")
    spoken = render(lang, template, ctx)
    send_voice(ticket["phone"], lang, template, ctx, ticket["id"])
    return {"ivr_says": spoken, "lang": lang, "status": status_key,
            "position": ctx["position"], "eta_minutes": ctx["eta"]}


@router.post("/self-checkin")
def self_checkin(body: SelfCheckInIn):
    """GPS self check-in: farmer arrives on-site and checks in from the PWA
    without queueing at a desk. Geofence-verified against the mandi location."""
    from .config import settings
    ticket = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    if ticket["status"] != "SLOT_BOOKED":
        raise HTTPException(status_code=409, detail=f"Cannot check in from status {ticket['status']}")
    mandi = query_one("SELECT * FROM mandis WHERE id = ?", (ticket["mandi_id"],))
    distance = _haversine_km(body.lat, body.lng, mandi["lat"], mandi["lng"])
    if distance > settings.self_checkin_radius_km:
        raise HTTPException(status_code=422, detail=
            f"You appear to be {distance:.1f} km away. Please check in at the centre.")
    execute("UPDATE tickets SET status = 'ARRIVED', checked_in_at = ? WHERE id = ?",
            (now_iso(), ticket["id"]))
    log_event(ticket["mandi_id"], f"FARMER:{ticket['phone']}", "ARRIVAL_VERIFIED",
              {"token": body.token, "method": "GPS_SELF_CHECKIN", "distance_km": round(distance, 2)},
              ticket["id"])
    snap = recompute_mandi(ticket["mandi_id"])
    mine = next((q for q in snap["queue"] if q["ticket_id"] == ticket["id"]), None)
    send_sms(ticket["phone"], ticket["lang"], "ARRIVAL_CONFIRMED",
             {"token": body.token, "position": mine["position"] if mine else 0,
              "eta": int(mine["eta_minutes"] or 0) if mine else 0}, ticket["id"])
    return {"ok": True, "token": body.token, "method": "GPS_SELF_CHECKIN",
            "position": mine["position"] if mine else 0,
            "eta_minutes": int(mine["eta_minutes"] or 0) if mine else 0}


@router.post("/alerts/ack")
def ack_alert(body: AckIn):
    """Farmer acknowledges the leave-home alert (from app or IVR key-press).
    Stops the escalation ladder."""
    ticket = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    execute("UPDATE tickets SET alert_ack_at = ? WHERE id = ?", (now_iso(), ticket["id"]))
    log_event(ticket["mandi_id"], f"FARMER:{ticket['phone']}", "ALERT_ACKED", {"token": body.token}, ticket["id"])
    return {"ok": True, "token": body.token}


@router.get("/qrcode/{token}")
def qrcode(token: str):
    """Scannable QR of the token for gate verification (SVG, no deps)."""
    from .qrcode_svg import qr_svg
    ticket = query_one("SELECT token FROM tickets WHERE token = ?", (token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    svg = qr_svg(f"MANDIMITRA:{token}")
    from fastapi import Response
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/dispute")
def raise_dispute(body: DisputeIn):
    """Farmer raises a dispute/evidence flag on their procurement.
    Creates an immutable audit entry staff and admins must address."""
    ticket = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    execute("UPDATE tickets SET dispute_count = dispute_count + 1 WHERE id = ?", (ticket["id"],))
    log_event(ticket["mandi_id"], f"FARMER:{ticket['phone']}", "DISPUTE_RAISED",
              {"token": body.token, "category": body.category, "note": body.note[:300]},
              ticket["id"])
    return {"ok": True, "token": body.token, "message":
            "Dispute recorded with timestamp. Use this record for review — it cannot be altered."}


@router.get("/disputes/mine")
def my_disputes(phone: str):
    rows = query(
        "SELECT ts, action, details FROM audit_events WHERE actor = ? AND action = 'DISPUTE_RAISED'"
        " ORDER BY id DESC LIMIT 20",
        (f"FARMER:{phone}",),
    )
    return {"count": len(rows), "disputes": [dict(r) for r in rows]}


@router.get("/board/{mandi_id}")
def public_board(mandi_id: str):
 """Public now-serving board for hall displays. No auth, read-only, large-text friendly."""
 snap = get_snapshot(mandi_id)
 serving = [q for q in snap["queue"] if q["queue_group"] == "SERVING"]
 next_up = [q for q in snap["queue"] if q["queue_group"] == "ARRIVED"][:5]
 mandi = query_one("SELECT name FROM mandis WHERE id = ?", (mandi_id,))
 return {
  "mandi_id": mandi_id,
  "mandi_name": mandi["name"] if mandi else mandi_id,
  "now_serving": [{"token": q["token"], "counter": None, "stage": q["status"]} for q in serving],
  "next_up": [{"token": q["token"], "position": q["position"], "eta_minutes": q["eta_minutes"]} for q in next_up],
  "queue_length": sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING"),
  "updated_at": snap["updated_at"],
 }


# ----------------------- Layer 2: discovery + assistant -------------------- #

@router.get("/discover")
def discover_centres(lat: float | None = None, lng: float | None = None,
                     crop: str | None = None, quantity_kg: float = 0, pin: str | None = None):
    """Nearby-centre discovery ranked by TOTAL JOURNEY time (travel + queue +
    processing), with status, rate (source-stamped) and experience rating."""
    from .discovery import discover
    return {"centres": discover(lat, lng, crop, quantity_kg, pin)}


@router.get("/best-for-me")
def best_for_me(lat: float | None = None, lng: float | None = None,
                crop: str = "Paddy", quantity_kg: float = 500):
    """'Best Mandi For Me' AI: ranks every centre on total journey time,
    availability and reputation, and explains the recommendation."""
    from .discovery import best_for_me as bfm
    return bfm(lat, lng, crop, quantity_kg)


class AssistantIn(BaseModel):
    question: str
    token: str | None = None
    phone: str | None = None
    role: str = "farmer"
    lat: float | None = None
    lng: float | None = None
    crop: str | None = None


@router.post("/assistant")
def assistant(body: AssistantIn):
    """Mandi Mitra assistant: grounded in the RAG knowledge base and MCP-style
    tools — never free-form invention. Every dynamic answer cites its tool."""
    from .assistant import assistant_reply
    user = {"role": body.role, "token": body.token, "phone": body.phone,
            "lat": body.lat, "lng": body.lng, "crop": body.crop}
    return assistant_reply(body.question, user)


@router.get("/knowledge")
def knowledge_topics():
    """Browseable knowledge base (used for offline caching on the PWA)."""
    rows = query("SELECT title, source, updated, content FROM knowledge_docs ORDER BY id")
    return {"documents": [dict(r) for r in rows]}


@router.get("/why")
def why(token: str | None = None, mandi_id: str = "KL-KOCHI-01"):
    """Explainable AI: why is the wait what it is?"""
    from .explain import why_wait
    return why_wait(mandi_id, token)


class FeedbackIn(BaseModel):
    token: str
    ratings: dict  # waiting, staff, queue_mgmt, info, payment, facilities, overall (1-5)
    comment: str = ""


@router.post("/feedback")
def submit_feedback_ep(body: FeedbackIn):
    from .feedback import submit_feedback
    t = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not t:
        raise HTTPException(status_code=404, detail="Unknown token")
    return submit_feedback(body.token, t["phone"], t["mandi_id"], body.ratings, body.comment)


class GrievanceIn(BaseModel):
    token: str | None = None
    phone: str | None = None
    mandi_id: str | None = None
    category: str = "OTHER"
    description: str = ""


@router.post("/grievance")
def grievance(body: GrievanceIn):
    from .feedback import file_grievance
    token = body.token
    phone = body.phone
    mandi_id = body.mandi_id
    if token:
        t = query_one("SELECT * FROM tickets WHERE token = ?", (token,))
        if t:
            phone = phone or t["phone"]
            mandi_id = mandi_id or t["mandi_id"]
    if not phone or not mandi_id:
        raise HTTPException(status_code=422, detail="phone and mandi_id required (or a valid token)")
    return file_grievance(token, phone, mandi_id, body.category, body.description)


@router.get("/grievance/{grievance_id}")
def grievance_track(grievance_id: str):
    from .feedback import track_grievance
    g = track_grievance(grievance_id)
    if not g:
        raise HTTPException(status_code=404, detail="Unknown grievance ID")
    return g


@router.get("/grievances/mine")
def grievances_mine(phone: str):
    from .feedback import my_grievances
    return {"grievances": my_grievances(phone)}


# ----------------------- booking lifecycle extensions ---------------------- #

class RescheduleIn(BaseModel):
    token: str
    new_slot_time: str


@router.post("/reschedule")
def reschedule(body: RescheduleIn):
    t = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not t:
        raise HTTPException(status_code=404, detail="Unknown token")
    if t["status"] not in ("SLOT_BOOKED",):
        raise HTTPException(status_code=409, detail="Only SLOT_BOOKED tickets can be rescheduled")
    execute("UPDATE tickets SET slot_time = ? WHERE id = ?", (body.new_slot_time, t["id"]))
    log_event(t["mandi_id"], f"FARMER:{t['phone']}", "BOOKING_RESCHEDULED",
              {"token": body.token, "new_slot": body.new_slot_time}, t["id"])
    recompute_mandi(t["mandi_id"])
    return {"ok": True, "token": body.token, "new_slot_time": body.new_slot_time}


class CancelIn(BaseModel):
    token: str


@router.post("/cancel")
def cancel(body: CancelIn):
    t = query_one("SELECT * FROM tickets WHERE token = ?", (body.token,))
    if not t:
        raise HTTPException(status_code=404, detail="Unknown token")
    if t["status"] not in ("SLOT_BOOKED", "ARRIVED"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel from {t['status']}")
    execute("UPDATE tickets SET status = 'CANCELLED' WHERE id = ?", (t["id"],))
    log_event(t["mandi_id"], f"FARMER:{t['phone']}", "BOOKING_CANCELLED", {"token": body.token}, t["id"])
    recompute_mandi(t["mandi_id"])
    return {"ok": True, "token": body.token}


@router.get("/profile")
def profile(phone: str):
    """Auto-fill: verified profile for one-tap booking (no repeated typing)."""
    farmer = query_one("SELECT phone, mm_id, name, lang FROM farmers WHERE phone = ?", (phone,))
    if not farmer:
        raise HTTPException(status_code=404, detail="Unknown farmer")
    last = query_one(
        "SELECT crop, quantity_kg, mandi_id FROM tickets WHERE phone = ? ORDER BY id DESC LIMIT 1",
        (phone,),
    )
    tickets = query_one(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS c FROM tickets WHERE phone = ?",
        (phone,),
    )
    return {"farmer": dict(farmer),
            "defaults": {"crop": last["crop"] if last else "Paddy",
                         "quantity_kg": last["quantity_kg"] if last else 500,
                         "mandi_id": last["mandi_id"] if last else "KL-KOCHI-01"},
            "history": {"bookings": tickets["n"], "completed": tickets["c"]}}


@router.get("/mandis")
def mandis():
    rows = query("SELECT id, name, district, lat, lng, opens_at, closes_at FROM mandis")
    out = []
    for r in rows:
        snap = get_snapshot(r["id"])
        waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
        level = "HIGH" if waiting >= 25 else "MODERATE" if waiting >= 10 else "LOW"
        out.append({**dict(r), "queue_length": waiting, "congestion": level,
                    "processed_today": snap["processed_today"]})
    return {"mandis": out}
