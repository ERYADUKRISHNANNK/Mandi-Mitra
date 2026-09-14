"""Live Mode — a background heartbeat that makes the centre behave like a
real procurement day.

When enabled, a daemon thread ticks every few seconds and drives ONE
realistic event per mandi per tick, through the SAME audited functions the
staff dashboard uses (check-in, walk-in, weighing, quality, payment,
no-show). Every event recomputes the queue and fans out a WebSocket
update — so the farmer PWA, staff dashboard, hall board and maps all move
live with zero clicks.

This is a demonstration aid for the prototype; in deployment the same
events arrive from real gate scans, counter terminals and payment gateways.
"""

import random
import threading
import time
import traceback

from .audit import log_event
from .db import execute, now_iso, query, query_one, today_str

STATE = {
    "on": False,
    "stop": threading.Event(),
    "thread": None,
    "tick_seconds": 4.0,
    "events": 0,
}

CROPS = ["Paddy", "Wheat", "Maize"]
VEHICLES = ["Tractor", "Truck", "Mini truck", "Auto", None]
FIRST = ["Rajan", "Meera", "Suresh", "Lakshmi", "Anil", "Devika", "Manoj", "Kavya", "Vijay", "Radha"]
LANGS = ["ml", "ml", "ml", "en", "hi", "ta"]


def _scoped_user(mandi_id: str) -> dict:
    """Live-mode acts per-mandi with staff authority, exactly like the
    dashboard actions it reuses."""
    return {"username": "live-mode", "role": "STAFF", "mandi_id": mandi_id}


def _random_phone() -> str:
    return "9" + "".join(random.choice("0123456789") for _ in range(9))


def _pay_off(mandi_id: str, token: str):
    """Complete a payment exactly like the staff Pay action."""
    from . import receipts
    t = query_one("SELECT * FROM tickets WHERE mandi_id = ? AND token = ?", (mandi_id, token))
    if not t:
        return
    execute(
        "UPDATE tickets SET status = 'COMPLETED', payment_status = 'COMPLETED',"
        " payment_completed_at = ?, completed_at = ? WHERE id = ?",
        (now_iso(), now_iso(), t["id"]),
    )
    log_event(mandi_id, "LIVE", "PAYMENT_COMPLETED", {"token": token}, t["id"])
    receipts.mint_receipt(t)


def _tick_mandi(mandi_id: str):
    from .routes_staff import (
        CheckInIn, CompleteIn, StageIn, WalkInIn,
        checkin, complete_procurement, walkin, _start_stage,
    )
    user = _scoped_user(mandi_id)
    date = today_str()
    r = random.random()
    done = False

    if r < 0.45:  # a booked farmer arrives at the gate
        nxt = query_one(
            "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'SLOT_BOOKED'"
            " ORDER BY slot_time LIMIT 1",
            (mandi_id, date),
        )
        if nxt:
            checkin(CheckInIn(token=nxt["token"]), user)
            done = True
        r = 0.6 if not done else 1.0  # fall through to walk-in if nobody left
    if not done and r < 0.62:  # a walk-in takes a token at the kiosk
        try:
            walkin(WalkInIn(
                farmer_name=f"{random.choice(FIRST)} {random.choice(FIRST)}",
                phone=_random_phone(), crop=random.choice(CROPS),
                quantity_kg=random.choice([100, 250, 500, 750, 1000]),
                lang=random.choice(LANGS), vehicle_type=random.choice(VEHICLES),
                mandi_id=mandi_id,
            ), user)
            done = True
        except Exception:
            pass
        r = 0.85 if not done else 1.0
    if not done and r < 0.85:  # the counter advances the serving farmer
        serving = query_one(
            "SELECT token, status FROM tickets WHERE mandi_id = ? AND slot_date = ?"
            " AND status IN ('WEIGHING','QUALITY_CHECK') ORDER BY stage_started_at LIMIT 1",
            (mandi_id, date),
        )
        if serving:
            if serving["status"] == "WEIGHING":
                _start_stage(StageIn(token=serving["token"]), user, "QUALITY_CHECK")
            else:
                complete_procurement(
                    CompleteIn(token=serving["token"], quality_grade=random.choice(["A", "A", "B"])), user)
            done = True
        r = 0.95 if not done else 1.0
    if not done and r < 0.95:  # a payment lands
        pay = query_one(
            "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'PAYMENT'"
            " AND payment_status IN ('PROCESSING','DELAYED') LIMIT 1",
            (mandi_id, date),
        )
        if pay:
            _pay_off(mandi_id, pay["token"])
            done = True
        r = 1.0 if not done else 1.0
    if not done:  # rare no-show (only when enough farmers are still booked)
        booked = query(
            "SELECT token FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status = 'SLOT_BOOKED'",
            (mandi_id, date),
        )
        if len(booked) > 4:
            unlucky = random.choice(booked)
            t = query_one("SELECT id FROM tickets WHERE mandi_id = ? AND token = ?", (mandi_id, unlucky["token"]))
            if t:
                execute("UPDATE tickets SET status = 'NO_SHOW', no_shown_at = ? WHERE id = ?",
                        (now_iso(), t["id"]))
                log_event(mandi_id, "LIVE", "NO_SHOW_MARKED", {"token": unlucky["token"]}, t["id"])


def _loop():
    while not STATE["stop"].is_set():
        try:
            for row in query("SELECT id FROM mandis"):
                _tick_mandi(row["id"])
                STATE["events"] += 1
        except Exception:
            traceback.print_exc()
        STATE["stop"].wait(STATE["tick_seconds"])


def start(tick_seconds: float = 4.0):
    if STATE["on"]:
        STATE["tick_seconds"] = max(1.5, tick_seconds)
        return
    STATE["tick_seconds"] = max(1.5, tick_seconds)
    STATE["stop"].clear()
    STATE["thread"] = threading.Thread(target=_loop, daemon=True, name="mandi-live-mode")
    STATE["thread"].start()
    STATE["on"] = True


def stop():
    STATE["stop"].set()
    STATE["on"] = False


def status() -> dict:
    return {
        "live": STATE["on"],
        "tick_seconds": STATE["tick_seconds"],
        "events_processed": STATE["events"],
        "note": "Live Mode drives arrivals, weighing, quality, payments and occasional no-shows through the audited staff actions; every change is broadcast over WebSocket.",
    }
