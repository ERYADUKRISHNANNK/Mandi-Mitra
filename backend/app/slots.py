"""Smart slot recommendation.

Scores candidate slots for a farmer's requested day using:
  - expected arrivals per hour (historical profile + congestion forecast)
  - active counter capacity and average processing time
  - load already booked into each candidate slot
Recommends the slot with the lowest predicted waiting time and attaches a
confidence score, queue depth and expected wait for transparency.
"""

import random
from datetime import datetime, timedelta

from .db import query, query_one

CANDIDATE_START = 8   # 08:00
CANDIDATE_END = 16    # last slot 16:00
SLOT_MINUTES = 30
PER_SLOT_CAPACITY = 6  # farmers per 30-min slot per mandi (prototype constant)


def _history_profile(mandi_id: str) -> dict[int, float]:
    rows = query(
        "SELECT hour, AVG(arrivals) AS a FROM history_stats WHERE mandi_id = ? GROUP BY hour",
        (mandi_id,),
    )
    return {r["hour"]: float(r["a"]) for r in rows}


def _avg_process_minutes(mandi_id: str) -> float:
    row = query_one(
        """
        SELECT AVG((julianday(completed_at) - julianday(stage_started_at)) * 1440) AS m
        FROM tickets
        WHERE mandi_id = ? AND completed_at IS NOT NULL AND stage_started_at IS NOT NULL
          AND (julianday(completed_at) - julianday(stage_started_at)) * 1440 BETWEEN 0 AND 60
        """,
        (mandi_id,),
    )
    if row and row["m"]:
        return min(15.0, max(3.0, row["m"]))
    return 6.0


def recommend_slots(mandi_id: str, slot_date: str | None = None, quantity_kg: float = 0) -> dict:
    slot_date = slot_date or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    is_today = slot_date == now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    # Evening fallback: when every today-slot has passed (or the date is in the
    # past), recommend tomorrow's slots so farmers always get a usable answer.
    if slot_date < now.strftime("%Y-%m-%d"):
        slot_date = tomorrow
        is_today = False
    if is_today and now.hour >= CANDIDATE_END:
        slot_date, is_today = tomorrow, False

    counters = query_one(
        "SELECT COUNT(*) AS n FROM counters WHERE mandi_id = ? AND is_active = 1", (mandi_id,)
    )
    n_counters = counters["n"] if counters else 1
    proc = _avg_process_minutes(mandi_id)
    profile = _history_profile(mandi_id)

    booked = {
        r["slot_time"]: r["n"]
        for r in query(
            """
            SELECT slot_time, COUNT(*) AS n FROM tickets
            WHERE mandi_id = ? AND slot_date = ?
              AND status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')
            GROUP BY slot_time
            """,
            (mandi_id, slot_date),
        )
    }

    options = []
    for minute in range(CANDIDATE_START * 60, CANDIDATE_END * 60 + 1, SLOT_MINUTES):
        hh, mm = divmod(minute, 60)
        slot_time = f"{hh:02d}:{mm:02d}"
        if is_today and datetime.now() >= now.replace(hour=hh, minute=mm, second=0, microsecond=0):
            continue  # slot already passed

        hour = hh
        expected_arrivals = profile.get(hour, 6.0)
        load = booked.get(slot_time, 0)
        capacity = max(1, int(n_counters * 60 / (proc * 2)))  # per slot throughput
        headroom = max(0, capacity + PER_SLOT_CAPACITY - load)
        # Predicted wait: queue ahead / throughput, nudged by expected crowd.
        ahead = load + expected_arrivals * 0.25
        wait = (ahead * proc) / max(1, n_counters)
        confidence = round(max(0.55, min(0.95, 0.95 - wait / 120 - load * 0.01)), 2)

        options.append({
            "slot_time": slot_time,
            "queue_ahead": int(load),
            "expected_wait_min": round(wait, 0),
            "confidence": confidence,
            "headroom": headroom,
            "recommended": False,
        })

    # Randomise ties slightly so repeated calls vary a little but stay stable enough.
    random.seed(f"{mandi_id}{slot_date}{quantity_kg}")
    options.sort(key=lambda o: (o["expected_wait_min"] + random.random() * 3, o["slot_time"]))
    for i, o in enumerate(options[:3]):
        o["rank"] = i + 1
    if options:
        options[0]["recommended"] = True

    return {
        "mandi_id": mandi_id,
        "slot_date": slot_date,
        "based_on": {
            "counters_active": n_counters,
            "avg_process_minutes": proc,
            "capacity_per_slot": PER_SLOT_CAPACITY,
        },
        "options": options[:12],
    }
