"""Live queue engine — the heart of Mandi Mitra.

Recomputes, per mandi and per date:
  - the ordered queue across the workflow Slot Booked -> Arrived -> Weighing
    -> Quality Check -> Payment -> Completed
  - every waiting farmer's live position (being served = position 0)
  - ETA via the prediction layer (model when available, analytic otherwise)
  - leave-home / turn-approaching triggers with simulated SMS + IVR calls
  - payment-delay detection

Runs entirely from SQLite state so every recomputation is replayable and
auditable; Redis-style hot state is emulated by the in-memory snapshot.
"""

from datetime import datetime

from .config import settings
from .db import execute, now_iso, query, query_one, today_str
from .notify import send_sms, send_voice
from .predictor import predict_bundle, predict_wait

QUEUE_SNAPSHOT: dict = {}  # mandi_id -> {"date": str, "queue": [dict]}


# --- helpers ---------------------------------------------------------------

def _parse_hhmm(value: str) -> float:
    try:
        h, m = value.split(":")
        return int(h) + int(m) / 60.0
    except Exception:
        return 0.0


def _minutes_until_slot(slot_date: str, slot_time: str, now_dt: datetime) -> float:
    try:
        target = datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
        return (target - now_dt).total_seconds() / 60.0
    except Exception:
        return 0.0


def _fmt_clock(minutes_ahead: float) -> str:
    dt = datetime.now().replace(second=0, microsecond=0)
    dt = dt.timestamp() + max(0.0, minutes_ahead) * 60
    return datetime.fromtimestamp(dt).strftime("%I:%M %p").lstrip("0")


def _stage_waits() -> dict:
    """Average minutes per stage from completed tickets, with sane defaults."""
    row = query_one(
        """
        SELECT AVG(quality_delay) AS q, AVG(payment_delay) AS p FROM (
            SELECT
              (julianday(completed_at) - julianday(stage_started_at)) * 1440 AS quality_delay,
              NULL AS payment_delay
            FROM tickets
            WHERE status = 'COMPLETED' AND stage_started_at IS NOT NULL
        )
        """
    )
    quality = row["q"] if row and row["q"] else 8.0
    payment = 6.0
    return {"QUALITY_CHECK": min(quality, 15.0), "PAYMENT": payment}


def _counters(mandi_id: str) -> list:
    rows = query(
        "SELECT * FROM counters WHERE mandi_id = ? AND is_active = 1 ORDER BY id", (mandi_id,)
    )
    return [dict(r) for r in rows]


def _avg_process_minutes(rows: list) -> float:
    durations = []
    for r in rows:
        if r["stage_started_at"] and r["completed_at"]:
            delta = _parse_ts(r["completed_at"]) - _parse_ts(r["stage_started_at"])
            if 0 < delta < 120:
                durations.append(delta)
    return round(sum(durations) / len(durations), 1) if durations else 6.0


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return None


# --- core recomputation -----------------------------------------------------

def recompute_mandi(mandi_id: str):
    """Rebuild the live queue snapshot for one mandi for today and push
    real-time updates. Call after any arrival, stage move or counter change."""
    date = today_str()
    now_dt = datetime.now()
    hour = now_dt.hour

    counters = _counters(mandi_id)
    n_counters = len(counters) or 1

    waiting_rows = query(
        """
        SELECT * FROM tickets
        WHERE mandi_id = ? AND slot_date = ?
          AND status IN ('SLOT_BOOKED','ARRIVED','NO_SHOW')
        ORDER BY priority DESC, slot_time, id
        """,
        (mandi_id, date),
    )
    serving_rows = query(
        """
        SELECT * FROM tickets
        WHERE mandi_id = ? AND slot_date = ? AND status IN ('WEIGHING','QUALITY_CHECK')
        """,
        (mandi_id, date),
    )
    today_all = query(
        "SELECT * FROM tickets WHERE mandi_id = ? AND slot_date = ?", (mandi_id, date)
    )

    processed_today = sum(1 for r in today_all if r["status"] == "COMPLETED")
    arrivals_today = sum(1 for r in today_all if r["status"] in ("ARRIVED", "WEIGHING", "QUALITY_CHECK", "PAYMENT", "COMPLETED"))
    avg_process = _avg_process_minutes(today_all)
    history_row = query_one(
        "SELECT COUNT(*) AS n FROM history_stats WHERE mandi_id = ?", (mandi_id,)
    )
    has_history = history_row["n"] > 0 if history_row else False

    # --- 1. Serving farmers: quality-check queues behind current weighing ---
    stage_waits = _stage_waits()
    queue = []
    for r in serving_rows:
        item = dict(r)
        if r["status"] == "WEIGHING":
            w = predict_bundle([avg_process * 0.4, stage_waits["QUALITY_CHECK"]], 0.8)
            item["position"] = 0
        else:
            w = {"eta_minutes": stage_waits["QUALITY_CHECK"], "confidence": 0.8}
            item["position"] = 0
        item["eta_minutes"] = w["eta_minutes"]
        item["eta_confidence"] = w["confidence"]
        item["queue_group"] = "SERVING"
        queue.append(item)

    # --- 2. Waiting farmers (ARRIVED), then pre-arrivals (SLOT_BOOKED/NO_SHOW) ---
    arrived = [dict(r) for r in waiting_rows if r["status"] == "ARRIVED"]
    pre = [dict(r) for r in waiting_rows if r["status"] in ("SLOT_BOOKED", "NO_SHOW")]

    position_cursor = len(queue)
    for group in (arrived, pre):
        for r in group:
            position_cursor += 1
            r["position"] = position_cursor
            r["queue_group"] = "ARRIVED" if r["status"] == "ARRIVED" else "UPCOMING"
            waits = []
            conf = 0.6
            if has_history:
                res = predict_wait(
                    position=r["position"],
                    avg_process_minutes=avg_process,
                    counters_active=n_counters,
                    hour=hour,
                    arrivals=arrivals_today,
                    processed=processed_today,
                )
                waits.append(res["eta_minutes"])
                conf = res["confidence"]
            else:
                res, conf = None, 0.55
            if r["status"] == "ARRIVED":
                waits.append(stage_waits["QUALITY_CHECK"])
            waits.append(stage_waits["PAYMENT"])
            if res:
                w = predict_bundle(waits, conf)
            else:
                # Pure analytic: arrival wait + stage waits
                ahead = max(0, r["position"] - 1)
                analytic = ahead * (avg_process / n_counters) if r["status"] == "ARRIVED" else \
                    _minutes_until_slot(r["slot_date"], r["slot_time"], now_dt) + ahead * (avg_process / n_counters)
                w = predict_bundle([max(0.0, analytic)] + (waits[1:] if r["status"] == "ARRIVED" else waits), conf)
            r["eta_minutes"] = w["eta_minutes"]
            r["eta_confidence"] = w["confidence"]
            queue.append(r)

    # --- 3. Triggers: leave-home, turn-soon, payment delay -------------------
    for r in queue:
        _maybe_alert(r)

    _detect_payment_delays(mandi_id)

    snapshot = {
        "mandi_id": mandi_id,
        "date": date,
        "queue": queue,
        "counters_active": n_counters,
        "avg_process_minutes": avg_process,
        "arrivals_today": arrivals_today,
        "processed_today": processed_today,
        "updated_at": now_iso(),
    }
    QUEUE_SNAPSHOT[mandi_id] = snapshot

    public = _public_snapshot(snapshot)
    from .events import broadcast_sync
    broadcast_sync(mandi_id, "queue_update", public)
    return public


def _maybe_alert(r: dict):
    if r["status"] not in ("ARRIVED", "SLOT_BOOKED"):
        return
    ticket_id = r["id"]
    eta = r.get("eta_minutes") or 0.0

    # Leave-home: ETA under threshold and not already alerted.
    if r["status"] == "SLOT_BOOKED" and not r["leave_home_alerted"] and 0 < eta <= settings.leave_home_lead_minutes:
        ctx = {"token": r["token"], "eta_time": _fmt_clock(eta), "position": r["position"]}
        send_sms(r["phone"], r["lang"], "LEAVE_HOME", ctx, ticket_id)
        send_voice(r["phone"], r["lang"], "LEAVE_HOME", ctx, ticket_id)
        execute("UPDATE tickets SET leave_home_alerted = 1 WHERE id = ?", (ticket_id,))
        r["leave_home_alerted"] = 1

    # Turn-approaching: few farmers ahead and the farmer has arrived.
    if r["status"] == "ARRIVED" and not r["turn_soon_alerted"] and 0 < r["position"] <= settings.turn_soon_position:
        ctx = {"token": r["token"], "position": r["position"]}
        send_sms(r["phone"], r["lang"], "TURN_SOON", ctx, ticket_id)
        send_voice(r["phone"], r["lang"], "TURN_SOON", ctx, ticket_id)
        execute("UPDATE tickets SET turn_soon_alerted = 1 WHERE id = ?", (ticket_id,))
        r["turn_soon_alerted"] = 1


def _detect_payment_delays(mandi_id: str):
    row = query_one(
        """
        SELECT id, token, phone, lang, payment_submitted_at FROM tickets
        WHERE mandi_id = ? AND status = 'PAYMENT'
          AND payment_status = 'PROCESSING' AND payment_delayed = 0
          AND payment_submitted_at IS NOT NULL
          AND (julianday('now', 'localtime') - julianday(payment_submitted_at)) * 1440 >= ?
        """,
        (mandi_id, settings.payment_delay_minutes),
    )
    if not row:
        return
    execute("UPDATE tickets SET payment_status = 'DELAYED', payment_delayed = 1 WHERE id = ?", (row["id"],))
    send_sms(row["phone"], row["lang"], "PAYMENT_DELAY", {"token": row["token"]}, row["id"])


def _public_snapshot(snapshot: dict) -> dict:
    queue_view = [
        {
            "ticket_id": r["id"],
            "token": r["token"],
            "status": r["status"],
            "position": r["position"],
            "eta_minutes": round(r["eta_minutes"], 1) if r["eta_minutes"] is not None else None,
            "eta_confidence": r.get("eta_confidence"),
            "queue_group": r.get("queue_group"),
            "farmer_name": r["farmer_name"],
            "crop": r["crop"],
            "quantity_kg": r["quantity_kg"],
            "slot_time": r["slot_time"],
            "priority": r["priority"],
            "leave_home_alerted": bool(r.get("leave_home_alerted")),
            "turn_soon_alerted": bool(r.get("turn_soon_alerted")),
        }
        for r in snapshot["queue"]
    ]
    return {
        "mandi_id": snapshot["mandi_id"],
        "date": snapshot["date"],
        "queue": queue_view,
        "counters_active": snapshot["counters_active"],
        "avg_process_minutes": snapshot["avg_process_minutes"],
        "arrivals_today": snapshot["arrivals_today"],
        "processed_today": snapshot["processed_today"],
        "updated_at": snapshot["updated_at"],
    }


# --- queries ----------------------------------------------------------------

def get_snapshot(mandi_id: str):
    snap = QUEUE_SNAPSHOT.get(mandi_id)
    if snap is None:
        snap = recompute_mandi(mandi_id)
    return _public_snapshot(snap)


def get_ticket_public(ticket) -> dict:
    r = dict(ticket)
    return {
        "ticket_id": r["id"],
        "token": r["token"],
        "mandi_id": r["mandi_id"],
        "phone": r["phone"],
        "farmer_name": r["farmer_name"],
        "crop": r["crop"],
        "quantity_kg": r["quantity_kg"],
        "slot_date": r["slot_date"],
        "slot_time": r["slot_time"],
        "lang": r["lang"],
        "status": r["status"],
        "position": r["position"],
        "eta_minutes": r["eta_minutes"],
        "eta_confidence": r.get("eta_confidence") if "eta_confidence" in r else None,
        "quality_grade": r["quality_grade"],
        "amount": r["amount"],
        "payment_status": r["payment_status"],
        "payment_delayed": bool(r["payment_delayed"]),
        "leave_home_alerted": bool(r["leave_home_alerted"]),
        "turn_soon_alerted": bool(r["turn_soon_alerted"]),
        "created_at": r["created_at"],
        "checked_in_at": r["checked_in_at"],
        "completed_at": r["completed_at"],
    }
