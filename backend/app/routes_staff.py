"""Staff and admin endpoints: operations, analytics, command centre, autopilot."""

import random

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from . import anomaly, congestion, receipts
from .audit import log_event
from .db import execute, now_iso, query, query_one, today_str
from .i18n import SUPPORTED_LANGS
from .notify import recent as recent_notifications
from .notify import send_sms
from .pricing import procurement_amount
from .queue_engine import get_snapshot, recompute_mandi
from .security import authenticate, create_jwt, verify_password

router = APIRouter(prefix="/api/staff", tags=["staff"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def staff_auth(authorization: str | None = Header(default=None)):
    user = authenticate(authorization, {"STAFF", "ADMIN"})
    if not user:
        raise HTTPException(status_code=401, detail="Staff or admin JWT required")
    user["username"] = user.get("sub")
    return user


def admin_auth(authorization: str | None = Header(default=None)):
    user = authenticate(authorization, {"ADMIN"})
    if not user:
        raise HTTPException(status_code=401, detail="Admin JWT required")
    user["username"] = user.get("sub")
    return user


# ------------------------------ models ------------------------------------ #

class LoginIn(BaseModel):
    username: str
    password: str


class StageIn(BaseModel):
    token: str
    counter_id: int | None = None


class CheckInIn(BaseModel):
    token: str


class NoShowIn(BaseModel):
    token: str
    requeue: bool = True


class CounterIn(BaseModel):
    counter_id: int
    is_active: bool


class CompleteIn(BaseModel):
    token: str
    quality_grade: str = "A"


class PayIn(BaseModel):
    token: str


class IVRBroadcastIn(BaseModel):
    lang: str = "ml"


class AutoIn(BaseModel):
    steps: int = 8
    mandi_id: str | None = None


# ------------------------------ helpers ----------------------------------- #

def _require_mandi(user: dict) -> str:
    mandi_id = user.get("mandi_id")
    if not mandi_id:
        raise HTTPException(status_code=403, detail="Admin account has no mandi scope — use the command centre")
    return mandi_id


def _mandi_stats(mandi_id: str) -> dict:
    date = today_str()
    stats = query_one(
        """
        SELECT
          SUM(CASE WHEN status = 'NO_SHOW' THEN 1 ELSE 0 END) AS no_shows,
          SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
          SUM(CASE WHEN status = 'PAYMENT' AND payment_status != 'COMPLETED' THEN 1 ELSE 0 END) AS payments_pending,
          SUM(CASE WHEN payment_delayed = 1 THEN 1 ELSE 0 END) AS payments_delayed,
          SUM(amount) AS amount_today
        FROM tickets WHERE mandi_id = ? AND slot_date = ?
        """,
        (mandi_id, date),
    )
    snap = get_snapshot(mandi_id)
    waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
    waits = [q["eta_minutes"] for q in snap["queue"] if q["queue_group"] == "ARRIVED" and q["eta_minutes"]]
    avg_wait = round(sum(waits) / len(waits), 1) if waits else 0.0
    counters = []
    for r in query("SELECT * FROM counters WHERE mandi_id = ? ORDER BY id", (mandi_id,)):
        token = None
        if r["current_ticket_id"]:
            t = query_one("SELECT token FROM tickets WHERE id = ?", (r["current_ticket_id"],))
            token = t["token"] if t else None
        counters.append({
            "id": r["id"], "code": r["code"], "type": r["type"],
            "is_active": bool(r["is_active"]), "current_ticket_id": r["current_ticket_id"],
            "ticket_token": token,
        })
    anomaly_scan = anomaly.scan(mandi_id)
    return {
        "mandi_id": mandi_id,
        "date": date,
        "queue_length": waiting,
        "avg_wait_minutes": avg_wait,
        "arrivals_today": snap["arrivals_today"],
        "processed_today": snap["processed_today"],
        "no_shows": stats["no_shows"] or 0 if stats else 0,
        "completed": stats["completed"] or 0 if stats else 0,
        "payments_pending": stats["payments_pending"] or 0 if stats else 0,
        "payments_delayed": stats["payments_delayed"] or 0 if stats else 0,
        "amount_today": round(stats["amount_today"] or 0, 2) if stats else 0,
        "avg_process_minutes": snap["avg_process_minutes"],
        "counters": counters,
        "anomaly_flags": anomaly_scan["flag_count"],
        "congestion_forecast": congestion.forecast(mandi_id),
    }


def _get_ticket(mandi_id: str, token: str):
    ticket = query_one("SELECT * FROM tickets WHERE token = ? AND mandi_id = ?", (token, mandi_id))
    if not ticket:
        raise HTTPException(status_code=404, detail="Token not found at this mandi")
    return ticket


def _release_counter_of(ticket_id: int):
    execute("UPDATE counters SET current_ticket_id = NULL WHERE current_ticket_id = ?", (ticket_id,))


def _assign_counter(mandi_id: str, ticket_id: int, counter_type: str, counter_id: int | None) -> int | None:
    if counter_id:
        counter = query_one("SELECT * FROM counters WHERE id = ? AND mandi_id = ?", (counter_id, mandi_id))
        if not counter:
            raise HTTPException(status_code=404, detail="Counter not found")
    else:
        c = query_one(
            "SELECT id FROM counters WHERE mandi_id = ? AND type = ? AND is_active = 1 AND current_ticket_id IS NULL ORDER BY id LIMIT 1",
            (mandi_id, counter_type),
        )
        if not c:
            c = query_one(
                "SELECT id FROM counters WHERE mandi_id = ? AND type = ? AND is_active = 1 ORDER BY id LIMIT 1",
                (mandi_id, counter_type),
            )
        counter_id = c["id"] if c else None
    if counter_id:
        execute("UPDATE counters SET current_ticket_id = ? WHERE id = ?", (ticket_id, counter_id))
    return counter_id


# ------------------------------ auth -------------------------------------- #

@router.post("/login")
def login(body: LoginIn):
    user = query_one("SELECT * FROM staff_users WHERE username = ?", (body.username,))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_jwt({"sub": user["username"], "role": user["role"], "mandi_id": user["mandi_id"], "name": user["name"]})
    log_event(user["mandi_id"], f"STAFF:{user['username']}", "LOGIN", {})
    return {"access_token": token, "token_type": "bearer", "role": user["role"],
            "mandi_id": user["mandi_id"], "name": user["name"]}


# ------------------------------ operations -------------------------------- #

@router.get("/dashboard")
def dashboard(user: dict = Depends(staff_auth)):
    return _mandi_stats(_require_mandi(user))


@router.get("/queue")
def queue(user: dict = Depends(staff_auth)):
    return get_snapshot(_require_mandi(user))


@router.post("/checkin")
def checkin(body: CheckInIn, user: dict = Depends(staff_auth)):
    mandi_id = _require_mandi(user)
    ticket = _get_ticket(mandi_id, body.token)
    if ticket["status"] != "SLOT_BOOKED":
        raise HTTPException(status_code=409, detail=f"Cannot check in from status {ticket['status']}")
    execute("UPDATE tickets SET status = 'ARRIVED', checked_in_at = ?, no_shown_at = NULL, priority = 0 WHERE id = ?",
            (now_iso(), ticket["id"]))
    log_event(mandi_id, f"STAFF:{user['username']}", "ARRIVAL_VERIFIED", {"token": body.token}, ticket["id"])
    snap = recompute_mandi(mandi_id)
    mine = next((q for q in snap["queue"] if q["ticket_id"] == ticket["id"]), None)
    position = mine["position"] if mine else 0
    eta = int(mine["eta_minutes"] or 0) if mine else 0
    send_sms(ticket["phone"], ticket["lang"], "ARRIVAL_CONFIRMED",
             {"token": body.token, "position": position, "eta": eta}, ticket["id"])
    return {"ok": True, "token": body.token, "position": position, "eta_minutes": eta}


@router.post("/start-weighing")
def start_weighing(body: StageIn, user: dict = Depends(staff_auth)):
    return _start_stage(body, user, "WEIGHING")


@router.post("/start-quality")
def start_quality(body: StageIn, user: dict = Depends(staff_auth)):
    return _start_stage(body, user, "QUALITY_CHECK")


def _start_stage(body: StageIn, user: dict, stage: str):
    mandi_id = _require_mandi(user)
    ticket = _get_ticket(mandi_id, body.token)
    if stage == "WEIGHING" and ticket["status"] != "ARRIVED":
        raise HTTPException(status_code=409, detail=f"Cannot start weighing from {ticket['status']}")
    if stage == "QUALITY_CHECK" and ticket["status"] != "WEIGHING":
        raise HTTPException(status_code=409, detail=f"Cannot start quality check from {ticket['status']}")
    _release_counter_of(ticket["id"])
    counter_type = "WEIGHING" if stage == "WEIGHING" else "QUALITY_CHECK"
    counter_id = _assign_counter(mandi_id, ticket["id"], counter_type, body.counter_id)
    execute("UPDATE tickets SET status = ?, stage_started_at = ? WHERE id = ?",
            (stage, now_iso(), ticket["id"]))
    log_event(mandi_id, f"STAFF:{user['username']}", stage, {"token": body.token}, ticket["id"])
    if stage == "WEIGHING":
        code_row = query_one("SELECT code FROM counters WHERE id = ?", (counter_id,)) if counter_id else None
        send_sms(ticket["phone"], ticket["lang"], "WEIGHING_STARTED",
                 {"token": body.token, "counter": code_row["code"] if code_row else "1"}, ticket["id"])
    recompute_mandi(mandi_id)
    return {"ok": True, "token": body.token, "status": stage, "counter_id": counter_id}


@router.post("/complete-procurement")
def complete_procurement(body: CompleteIn, user: dict = Depends(staff_auth)):
    """Quality verified -> MSP amount computed -> payment initiated."""
    mandi_id = _require_mandi(user)
    ticket = _get_ticket(mandi_id, body.token)
    if ticket["status"] != "QUALITY_CHECK":
        raise HTTPException(status_code=409, detail=f"Cannot complete from {ticket['status']}")
    grade = body.quality_grade if body.quality_grade in ("A", "B") else "A"
    amount = procurement_amount(ticket["crop"], grade, ticket["quantity_kg"])
    execute(
        "UPDATE tickets SET status = 'PAYMENT', quality_grade = ?, amount = ?, payment_status = 'PROCESSING',"
        " payment_submitted_at = ? WHERE id = ?",
        (grade, amount, now_iso(), ticket["id"]),
    )
    _release_counter_of(ticket["id"])
    log_event(mandi_id, f"STAFF:{user['username']}", "PROCUREMENT_APPROVED",
              {"token": body.token, "grade": grade, "amount": amount}, ticket["id"])
    send_sms(ticket["phone"], ticket["lang"], "QUALITY_CHECK",
             {"token": body.token, "grade": grade, "amount": int(amount)}, ticket["id"])
    send_sms(ticket["phone"], ticket["lang"], "PAYMENT_INITIATED",
             {"token": body.token, "amount": int(amount)}, ticket["id"])
    recompute_mandi(mandi_id)
    return {"ok": True, "token": body.token, "grade": grade, "amount": amount, "payment_status": "PROCESSING"}


@router.post("/complete-payment")
def complete_payment(body: PayIn, user: dict = Depends(staff_auth)):
    mandi_id = _require_mandi(user)
    ticket = _get_ticket(mandi_id, body.token)
    if ticket["status"] != "PAYMENT" or ticket["payment_status"] == "COMPLETED":
        raise HTTPException(status_code=409,
                            detail=f"Cannot complete payment from {ticket['status']}/{ticket['payment_status']}")
    execute(
        "UPDATE tickets SET status = 'COMPLETED', payment_status = 'COMPLETED',"
        " payment_completed_at = ?, completed_at = ? WHERE id = ?",
        (now_iso(), now_iso(), ticket["id"]),
    )
    log_event(mandi_id, f"STAFF:{user['username']}", "PAYMENT_COMPLETED", {"token": body.token}, ticket["id"])
    send_sms(ticket["phone"], ticket["lang"], "PAYMENT_RECEIVED",
             {"token": body.token, "amount": int(ticket["amount"] or 0)}, ticket["id"])
    rec = receipts.mint_receipt(ticket)
    recompute_mandi(mandi_id)
    return {"ok": True, "token": body.token, "amount": ticket["amount"],
            "receipt_id": rec["id"] if rec else None,
            "receipt_hash": (rec["hash"][:16] + "…") if rec else None}


@router.post("/no-show")
def no_show(body: NoShowIn, user: dict = Depends(staff_auth)):
    """Mark no-show; optionally requeue at the back of today's queue."""
    mandi_id = _require_mandi(user)
    ticket = _get_ticket(mandi_id, body.token)
    if ticket["status"] not in ("SLOT_BOOKED", "ARRIVED"):
        raise HTTPException(status_code=409, detail=f"Cannot no-show from {ticket['status']}")
    if body.requeue:
        now = now_iso()
        execute(
            "UPDATE tickets SET status = 'ARRIVED', no_shown_at = ?, priority = -1, checked_in_at = ?,"
            " turn_soon_alerted = 0 WHERE id = ?",
            (now, now, ticket["id"]),
        )
    else:
        execute("UPDATE tickets SET status = 'NO_SHOW', no_shown_at = ? WHERE id = ?", (now_iso(), ticket["id"]))
    log_event(mandi_id, f"STAFF:{user['username']}", "NO_SHOW_HANDLED",
              {"token": body.token, "requeued": body.requeue}, ticket["id"])
    if not body.requeue:
        send_sms(ticket["phone"], ticket["lang"], "NO_SHOW_REMINDER", {"token": body.token}, ticket["id"])
    recompute_mandi(mandi_id)
    return {"ok": True, "token": body.token, "requeued": body.requeue}


@router.post("/counter")
def toggle_counter(body: CounterIn, user: dict = Depends(staff_auth)):
    mandi_id = _require_mandi(user)
    counter = query_one("SELECT * FROM counters WHERE id = ? AND mandi_id = ?", (body.counter_id, mandi_id))
    if not counter:
        raise HTTPException(status_code=404, detail="Counter not found")
    if not body.is_active:
        _release_counter_of(counter["current_ticket_id"]) if counter["current_ticket_id"] else None
    execute("UPDATE counters SET is_active = ?, current_ticket_id = CASE WHEN ? = 1 THEN current_ticket_id ELSE NULL END WHERE id = ?",
            (1 if body.is_active else 0, 1 if body.is_active else 0, body.counter_id))
    log_event(mandi_id, f"STAFF:{user['username']}", "COUNTER_" + ("ONLINE" if body.is_active else "OFFLINE"),
              {"counter": counter["code"]}, None)
    recompute_mandi(mandi_id)
    return {"ok": True, "counter_id": body.counter_id, "is_active": body.is_active}


# ------------------------------ intelligence ------------------------------ #

@router.get("/notifications")
def notifications(limit: int = 60, user: dict = Depends(staff_auth)):
    return {"notifications": recent_notifications(limit)}


@router.get("/anomalies")
def anomalies(user: dict = Depends(staff_auth)):
    return anomaly.scan(_require_mandi(user))


@router.get("/bottleneck")
def bottleneck(user: dict = Depends(staff_auth)):
    """Decision support: counter utilisation + staffing recommendations."""
    mandi_id = _require_mandi(user)
    snap = get_snapshot(mandi_id)
    waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
    counters = [dict(r) for r in query("SELECT * FROM counters WHERE mandi_id = ? ORDER BY id", (mandi_id,))]
    active = [c for c in counters if c["is_active"]]
    busy = [c for c in active if c["current_ticket_id"]]
    advice = []
    if active and len(busy) < len(active):
        idle = [c["code"] for c in active if not c["current_ticket_id"]]
        advice.append(f"Counter(s) {', '.join(idle)} idle while {waiting} farmers wait - allocate staff now.")
    elif len(active) > 1 and len(busy) == len(active):
        advice.append("All counters busy - consider opening standby capacity before peak hours.")
    if waiting >= 25:
        advice.append("Queue length high - broadcast IVR updates and stagger upcoming arrivals.")
    if snap["avg_process_minutes"] > 10:
        advice.append(f"Average processing is {snap['avg_process_minutes']} min - check weighing equipment.")
    utilisation = {c["code"]: (100 if c["current_ticket_id"] else 0) for c in active}
    return {"mandi_id": mandi_id, "queue_length": waiting,
            "counters_active": len(active), "counters_busy": len(busy),
            "utilisation": utilisation, "recommendations": advice}


@router.post("/ivr-broadcast")
def ivr_broadcast(body: IVRBroadcastIn, user: dict = Depends(staff_auth)):
    """Multilingual IVR/SMS broadcast to all pre-arrival farmers (congestion relief valve)."""
    mandi_id = _require_mandi(user)
    lang = body.lang if body.lang in SUPPORTED_LANGS else "ml"
    snap = get_snapshot(mandi_id)
    sent = 0
    for q in snap["queue"]:
        if q["queue_group"] == "UPCOMING":
            ticket = query_one("SELECT * FROM tickets WHERE id = ?", (q["ticket_id"],))
            if ticket:
                send_sms(ticket["phone"], lang, "LEAVE_HOME",
                         {"token": ticket["token"], "eta_time": "—", "position": q["position"]}, ticket["id"])
                sent += 1
    log_event(mandi_id, f"STAFF:{user['username']}", "IVR_BROADCAST", {"lang": lang, "sent": sent}, None)
    return {"ok": True, "sent": sent, "lang": lang}


@router.get("/receipts/verify")
def verify_receipts(user: dict = Depends(staff_auth)):
    return receipts.verify_chain()


# ------------------------------ admin ------------------------------------- #

@admin_router.get("/command-centre")
def command_centre(user: dict = Depends(admin_auth)):
    mandis = query("SELECT * FROM mandis")
    centres = []
    totals = {"farmers_today": 0, "completed": 0, "pending_payments": 0, "queue": 0, "amount_today": 0.0}
    for m in mandis:
        s = _mandi_stats(m["id"])
        level = "HIGH" if s["queue_length"] >= 25 else "MODERATE" if s["queue_length"] >= 10 else "LOW"
        totals["farmers_today"] += s["arrivals_today"] + s["queue_length"] + s["no_shows"]
        totals["completed"] += s["completed"]
        totals["pending_payments"] += s["payments_pending"] + s["payments_delayed"]
        totals["queue"] += s["queue_length"]
        totals["amount_today"] += s["amount_today"]
        centres.append({
            "mandi_id": m["id"], "name": m["name"], "district": m["district"],
            "lat": m["lat"], "lng": m["lng"], "queue_length": s["queue_length"],
            "congestion": level, "avg_wait": s["avg_wait_minutes"],
            "processed_today": s["processed_today"], "completed": s["completed"],
            "pending_payments": s["payments_pending"] + s["payments_delayed"],
            "anomaly_flags": s["anomaly_flags"],
            "avg_process_minutes": s["avg_process_minutes"],
        })
    congested = sum(1 for c in centres if c["congestion"] == "HIGH")
    moderate = sum(1 for c in centres if c["congestion"] == "MODERATE")
    return {
        "mandis_monitored": len(centres),
        "normal": len(centres) - congested - moderate,
        "moderate": moderate,
        "congested": congested,
        "totals": totals,
        "centres": centres,
        "receipt_chain": receipts.verify_chain(),
        "generated_at": now_iso(),
    }


@admin_router.get("/mandi/{mandi_id}")
def admin_mandi(mandi_id: str, user: dict = Depends(admin_auth)):
    return _mandi_stats(mandi_id)


@admin_router.get("/audit/{token}")
def audit_token(token: str, user: dict = Depends(admin_auth)):
    ticket = query_one("SELECT id FROM tickets WHERE token = ?", (token,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Unknown token")
    rows = query("SELECT ts, actor, action, details FROM audit_events WHERE ticket_id = ? ORDER BY id", (ticket["id"],))
    return {"token": token, "events": [dict(r) for r in rows]}


# --------------------------- demo autopilot ------------------------------- #

@router.post("/autopilot")
def autopilot(body: AutoIn, user: dict = Depends(staff_auth)):
    """Simulates real mandi activity so the demo can run hands-free."""
    mandi_id = body.mandi_id or _require_mandi(user)
    date = today_str()
    actions: list[str] = []
    try:
        for _ in range(max(1, body.steps)):
            # 1) Progress serving tickets one stage forward.
            serving = query(
                "SELECT token, status FROM tickets WHERE mandi_id = ? AND slot_date = ?"
                " AND status IN ('WEIGHING','QUALITY_CHECK') ORDER BY id",
                (mandi_id, date),
            )
            for s in serving:
                if s["status"] == "WEIGHING":
                    _start_stage(StageIn(token=s["token"]), user, "QUALITY_CHECK")
                else:
                    complete_procurement(CompleteIn(token=s["token"], quality_grade=random.choice(["A", "B"])), user)
                actions.append(f"{s['token']} advanced")
            # 2) A booked farmer arrives (checks in).
            nxt = query_one(
                "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'SLOT_BOOKED'"
                " ORDER BY slot_time LIMIT 1",
                (mandi_id, date),
            )
            if nxt:
                checkin(CheckInIn(token=nxt["token"]), user)
                actions.append(f"{nxt['token']} arrived")
            # 3) Move the next waiting farmer to a free weighing counter.
            free = query_one(
                "SELECT id FROM counters WHERE mandi_id = ? AND type = 'WEIGHING' AND is_active = 1"
                " AND current_ticket_id IS NULL LIMIT 1",
                (mandi_id,),
            )
            if free:
                waiting = query_one(
                    "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'ARRIVED'"
                    " AND priority >= 0 ORDER BY id LIMIT 1",
                    (mandi_id, date),
                )
                if waiting:
                    _start_stage(StageIn(token=waiting["token"], counter_id=free["id"]), user, "WEIGHING")
                    actions.append(f"{waiting['token']} → weighing")
            # 4) Complete one pending payment.
            pay = query_one(
                "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'PAYMENT'"
                " AND payment_status IN ('PROCESSING','DELAYED') LIMIT 1",
                (mandi_id, date),
            )
            if pay:
                _pay = _get_ticket(mandi_id, pay["token"])
                execute(
                    "UPDATE tickets SET status = 'COMPLETED', payment_status = 'COMPLETED',"
                    " payment_completed_at = ?, completed_at = ? WHERE id = ?",
                    (now_iso(), now_iso(), _pay["id"]),
                )
                log_event(mandi_id, "AUTOPILOT", "PAYMENT_COMPLETED", {"token": pay["token"]}, _pay["id"])
                receipts.mint_receipt(_pay)
                actions.append(f"{pay['token']} paid")
            if not actions:
                break
    finally:
        recompute_mandi(mandi_id)
    return {"ok": True, "steps": body.steps, "actions": actions}
