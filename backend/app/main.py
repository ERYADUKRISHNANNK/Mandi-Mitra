"""Mandi Mitra API — Smart Procurement Queue & Visibility System.

FastAPI application: farmer APIs, staff/admin APIs, WebSocket live queue,
simulated SMS / missed-call / IVR channels, and impact metrics.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import receipts
from .audit import log_event
from .db import execute, init_db, now_iso, query, query_one, today_str
from .events import manager
from .i18n import SUPPORTED_LANGS
from .notify import send_sms
from .predictor import train
from .queue_engine import get_snapshot, recompute_mandi
from .routes_farmer import router as farmer_router
from .routes_staff import admin_router as staff_admin_router
from .routes_staff import router as staff_router
from .seed import add_demo_queue, seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    add_demo_queue()
    train()
    yield


app = FastAPI(
    title="Mandi Mitra API",
    description="Smart Procurement Queue & Visibility System (SIH prototype)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype; restrict to the PWA origin in deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farmer_router)
app.include_router(staff_router)
app.include_router(staff_admin_router)


# ------------------------------ live updates ------------------------------- #

@app.websocket("/ws/{mandi_id}")
async def ws_queue(websocket: WebSocket, mandi_id: str):
    """Real-time queue feed per mandi: queue_update events on every change."""
    row = query_one("SELECT id FROM mandis WHERE id = ?", (mandi_id,))
    if not row:
        await websocket.close(code=4404)
        return
    await manager.connect(mandi_id, websocket)
    try:
        await websocket.send_json({"type": "queue_update", "mandi_id": mandi_id,
                                   "data": get_snapshot(mandi_id)})
        while True:
            await websocket.receive_text()  # keepalive pings from clients
    except WebSocketDisconnect:
        manager.disconnect(mandi_id, websocket)


# --------------------- simulated alternative channels ---------------------- #

class SmsIn(BaseModel):
    phone: str
    message: str  # e.g. "BOOK KL-KOCHI-01 PADDY 500 10:30 en"


class MissedCallIn(BaseModel):
    phone: str
    lang: str = "ml"


@app.post("/api/sms")
def sms_webhook(body: SmsIn):
    """Simulated SMS gateway inbound. Grammar (space separated):
    BOOK <MANDI> <CROP> <QTY> [HH:MM] [lang]   -> book a slot
    STATUS <TOKEN>                             -> live status by SMS
    HELP                                       -> usage
    """
    parts = body.message.strip().upper().split()
    if not parts:
        raise HTTPException(status_code=400, detail="Empty message")
    cmd = parts[0]

    if cmd == "BOOK":
        if len(parts) < 4:
            return _sms_reply(body.phone, "Usage: BOOK <mandi> <crop> <qty_kg> [HH:MM] [lang]")
        mandi_id, crop = parts[1], parts[2].capitalize()
        try:
            qty = float(parts[3])
        except ValueError:
            return _sms_reply(body.phone, "Quantity must be a number (kg).")
        slot_time = parts[4] if len(parts) > 4 and ":" in parts[4] else None
        lang = parts[5] if len(parts) > 5 and parts[5] in SUPPORTED_LANGS else "ml"

        from .slots import recommend_slots
        rec = recommend_slots(mandi_id, None, qty)
        if not slot_time:
            best = next((o for o in rec["options"] if o["recommended"]), rec["options"][0] if rec["options"] else None)
            if not best:
                return _sms_reply(body.phone, "No slots available today.")
            slot_time = best["slot_time"]
        ticket = query_one(
            "SELECT token FROM tickets WHERE phone = ? AND mandi_id = ? AND slot_date = ?"
            " AND status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')",
            (body.phone, mandi_id, today_str()),
        )
        if ticket:
            return _sms_reply(body.phone, f"Already booked: {ticket['token']}. Send STATUS {ticket['token']}")
        count = query_one("SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ?",
                          (mandi_id, today_str()))["n"]
        token = f"MND-{1000 + count + 1}"
        execute(
            "INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg, slot_date, slot_time, lang, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SLOT_BOOKED', ?)",
            (token, mandi_id, body.phone, f"Farmer {body.phone[-4:]}", crop, qty,
             today_str(), slot_time, lang, now_iso()),
        )
        t = query_one("SELECT id FROM tickets WHERE token = ?", (token,))
        log_event(mandi_id, f"SMS:{body.phone}", "BOOKING_CREATED", {"token": token, "channel": "SMS"}, t["id"])
        send_sms(body.phone, lang, "BOOKING_CONFIRMED",
                 {"token": token, "crop": crop, "date": today_str(), "time": slot_time}, t["id"])
        recompute_mandi(mandi_id)
        return _sms_reply(body.phone, f"Booked. Token {token}, slot {slot_time}. Reply STATUS {token} for updates.")
    elif cmd == "STATUS":
        token = parts[1] if len(parts) > 1 else None
        t = query_one("SELECT * FROM tickets WHERE token = ?", (token,)) if token else None
        if not t:
            return _sms_reply(body.phone, "Unknown token. Use STATUS <TOKEN>.")
        snap = recompute_mandi(t["mandi_id"])
        mine = next((q for q in snap["queue"] if q["ticket_id"] == t["id"]), None)
        pos = mine["position"] if mine else 0
        eta = int(mine["eta_minutes"] or 0) if mine else 0
        return _sms_reply(body.phone, f"Token {t['token']}: {t['status']}, position {pos}, ETA {eta} min.")
    else:
        return _sms_reply(body.phone, "Mandi Mitra: BOOK <mandi> <crop> <qty> [HH:MM] | STATUS <TOKEN> | HELP")


def _sms_reply(phone: str, text: str):
    execute(
        "INSERT INTO notifications (ticket_id, phone, channel, template_key, lang, body, simulated, created_at)"
        " VALUES (NULL, ?, 'SMS', 'DIRECT_REPLY', 'en', ?, 1, ?)",
        (phone, text, now_iso()),
    )
    return {"received_from": phone, "reply": text, "channel": "SMS (simulated gateway)"}


@app.post("/api/missed-call")
def missed_call(body: MissedCallIn):
    """Simulated missed-call channel: farmer gives a missed call, gets an
    instant IVR callback with their live status in their language."""
    lang = body.lang if body.lang in SUPPORTED_LANGS else "ml"
    t = query_one(
        "SELECT * FROM tickets WHERE phone = ? AND status IN"
        " ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT') ORDER BY id DESC LIMIT 1",
        (body.phone,),
    )
    if not t:
        return {"callback_status": "No active booking. SMS BOOK instructions sent.", "lang": lang}
    snap = recompute_mandi(t["mandi_id"])
    mine = next((q for q in snap["queue"] if q["ticket_id"] == t["id"]), None)
    pos = mine["position"] if mine else 0
    eta = int(mine["eta_minutes"] or 0) if mine else 0
    message = {
        "en": f"Token {t['token']}: position {pos}, expected in {eta} minutes.",
        "ml": f"ടോക്കൺ {t['token']}: സ്ഥാനം {pos}, {eta} മിനിറ്റിൽ തുടങ്ങും.",
        "hi": f"टोकन {t['token']}: स्थान {pos}, {eta} मिनट में।",
        "ta": f"டோக்கன் {t['token']}: இடம் {pos}, {eta} நிமிடத்தில்.",
    }[lang]
    log_event(t["mandi_id"], f"IVR:{body.phone}", "MISSED_CALL_STATUS", {"token": t["token"]}, t["id"])
    return {"callback_status": message, "token": t["token"], "position": pos,
            "eta_minutes": eta, "lang": lang, "channel": "IVR (simulated)"}


# ------------------------------ metrics & misc ------------------------------ #

@app.get("/api/impact")
def impact_metrics():
    """Before/after impact snapshot for the demo and the pitch."""
    rows = query(
        """
        SELECT mandi_id, COUNT(*) AS today_total,
          SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
          AVG(CASE WHEN completed_at IS NOT NULL AND checked_in_at IS NOT NULL
              THEN (julianday(completed_at) - julianday(checked_in_at)) * 1440 END) AS avg_time_in_mandi
        FROM tickets WHERE slot_date = ? GROUP BY mandi_id
        """,
        (today_str(),),
    )
    per_mandi = []
    for r in rows:
        t = (r["avg_time_in_mandi"] or 0)
        # Baseline: unmanged queues average ~4h at centre (SIH PS narrative).
        saved_min = max(0.0, 240 - t) if r["completed"] else 0
        per_mandi.append({
            "mandi_id": r["mandi_id"],
            "farmers_today": r["today_total"],
            "completed": r["completed"] or 0,
            "avg_time_in_mandi_min": round(t, 1),
            "farmer_hours_saved_today": round(saved_min * (r["completed"] or 0) / 60.0, 1),
        })
    total_saved = round(sum(m["farmer_hours_saved_today"] for m in per_mandi), 1)
    return {
        "baseline_unmanaged_wait_hours": 4,
        "per_mandi": per_mandi,
        "farmer_hours_saved_today": total_saved,
        "note": "Baseline 4h from PS narrative; live avg measured from checked-in to paid.",
    }


@app.get("/api/health")
def health():
    chain = receipts.verify_chain()
    return {"status": "ok", "service": "mandi-mitra", "receipt_chain_verified": chain["verified"],
            "time": now_iso()}
