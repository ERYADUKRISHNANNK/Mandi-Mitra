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


class IvrIn(BaseModel):
    phone: str | None = None
    token: str | None = None
    lang: str = "ml"


def _mm_id(phone: str) -> str:
    return "MM-" + hashlib.sha256(phone.encode()).hexdigest()[:6].upper()


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

    count = query_one(
        "SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ?",
        (body.mandi_id, slot_date),
    )["n"]
    token = f"MND-{1000 + count + 1}"

    execute(
        """
        INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg,
            slot_date, slot_time, lang, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SLOT_BOOKED', ?)
        """,
        (token, body.mandi_id, body.phone, body.farmer_name, body.crop, body.quantity_kg,
         slot_date, body.slot_time, body.lang, now_iso()),
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
