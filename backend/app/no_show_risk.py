"""AI module 4 — no-show risk scoring.

Estimates the probability that a booked farmer will not show up, from
behavioural and contextual signals:
  - historical no-show rate for the phone
  - booking lead time (same-hour bookings are riskier than next-day)
  - slot hour (early-morning and late-evening slots no-show more)
  - past completions (reliable farmers score lower)

Scores every SLOT_BOOKED ticket on each queue recomputation so staff can
proactively call or re-slot risky bookings. Transparent logistic-style blend
with declared weights — no black box.
"""

from datetime import datetime

from .db import query_one, execute

WEIGHTS = {
    "history_no_show": 0.45,
    "lead_time": 0.25,
    "slot_hour": 0.15,
    "completion_history": 0.15,
}


def score(ticket) -> dict:
    """Return {risk: 0..1, band, reasons} for a ticket row."""
    phone = ticket["phone"]
    reasons = []

    # 1) Historical no-show rate (default 0.12 prior when no history).
    row = query_one(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'NO_SHOW' THEN 1 ELSE 0 END) AS ns,"
        " SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS comp FROM tickets WHERE phone = ?",
        (phone,),
    )
    total = row["n"] or 0
    no_shows = row["ns"] or 0
    completions = row["comp"] or 0
    if total >= 2:
        hist = no_shows / total
        reasons.append(f"{no_shows}/{total} past no-shows")
    else:
        hist = 0.12
        reasons.append("new farmer (prior 12%)")

    # 2) Booking lead time in hours.
    try:
        created = datetime.fromisoformat(ticket["created_at"])
        slot_dt = datetime.strptime(f"{ticket['slot_date']} {ticket['slot_time']}", "%Y-%m-%d %H:%M")
        lead_h = (slot_dt - created).total_seconds() / 3600.0
    except Exception:
        lead_h = 2.0
    if lead_h <= 1:
        lead = 0.9
        reasons.append("booked <1h before slot")
    elif lead_h <= 3:
        lead = 0.6
        reasons.append("short lead time")
    elif lead_h <= 24:
        lead = 0.3
    else:
        lead = 0.1

    # 3) Slot hour pattern.
    try:
        hour = int(ticket["slot_time"].split(":")[0])
    except Exception:
        hour = 10
    if hour < 9 or hour >= 16:
        slot_h = 0.7
        reasons.append("edge-of-day slot")
    elif hour >= 13:
        slot_h = 0.4
    else:
        slot_h = 0.2

    # 4) Completion history (reliability lowers risk).
    comp_score = max(0.0, 0.6 - 0.2 * completions)
    if completions >= 3:
        reasons.append(f"{completions} reliable completions")

    risk = (WEIGHTS["history_no_show"] * hist + WEIGHTS["lead_time"] * lead
            + WEIGHTS["slot_hour"] * slot_h + WEIGHTS["completion_history"] * comp_score)
    risk = max(0.02, min(0.95, risk))

    if risk >= 0.6:
        band = "HIGH"
    elif risk >= 0.35:
        band = "MEDIUM"
    else:
        band = "LOW"

    return {"risk": round(risk, 2), "band": band, "reasons": reasons}
