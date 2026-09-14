"""Digital twin, capacity planner, bottleneck heatmap and quantity forecast.

The twin is a fast discrete simulation of a centre built from live parameters
(queue depth, per-farmer processing time, counter count) plus history-derived
arrival curves. What-if scenarios run in milliseconds — no side effects.
"""

from datetime import datetime, timedelta

from .db import query, query_one, today_str
from .queue_engine import get_snapshot


def _arrival_curve(mandi_id: str) -> dict[int, float]:
    rows = query(
        "SELECT hour, AVG(arrivals) AS a FROM history_stats WHERE mandi_id = ? GROUP BY hour",
        (mandi_id,),
    )
    return {r["hour"]: float(r["a"]) for r in rows}


def simulate(mandi_id: str, counters: int | None = None, proc_minutes: float | None = None,
             arrival_multiplier: float = 1.0, horizon_hours: int = 8) -> dict:
    """Simulate the rest of the day. Baseline uses live values unless overridden."""
    snap = get_snapshot(mandi_id)
    base_counters = snap["counters_active"] or 1
    base_proc = snap["avg_process_minutes"] or 6.0
    n_counters = counters if counters is not None else base_counters
    proc = proc_minutes if proc_minutes is not None else base_proc

    queue = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
    curve = _arrival_curve(mandi_id)
    now = datetime.now()
    t = now.replace(minute=0, second=0, microsecond=0)
    q = float(queue)
    peak_q = q
    served = 0.0
    timeline = []
    for step in range(horizon_hours):
        hour = (t + timedelta(hours=step)).hour
        arrivals = curve.get(hour, 6.0) * arrival_multiplier
        capacity = 60.0 / proc * n_counters
        q = max(0.0, q + arrivals - capacity)
        served += min(q + arrivals, capacity)
        peak_q = max(peak_q, q)
        timeline.append({"hour": f"{hour:02d}:00", "queue_end": round(q), "arrivals": round(arrivals)})
    eta_now = queue * proc / n_counters
    return {
        "mandi_id": mandi_id,
        "scenario": {"counters": n_counters, "proc_minutes": proc,
                     "arrival_multiplier": arrival_multiplier},
        "baseline": {"counters": base_counters, "proc_minutes": base_proc},
        "current_queue": queue,
        "eta_now_minutes": round(eta_now),
        "projected_end_queue": round(q),
        "peak_queue": round(peak_q),
        "projected_served_today": round(served),
        "timeline": timeline,
    }


def compare_scenarios(mandi_id: str) -> dict:
    base = simulate(mandi_id)
    plus_one = simulate(mandi_id, counters=base["scenario"]["counters"] + 1)
    minus_one = simulate(mandi_id, counters=max(1, base["scenario"]["counters"] - 1))
    faster = simulate(mandi_id, proc_minutes=max(2.0, base["baseline"]["proc_minutes"] * 0.8))
    surge = simulate(mandi_id, arrival_multiplier=1.5)
    return {
        "baseline": base,
        "open_plus_one": {"eta_now_minutes": plus_one["eta_now_minutes"],
                          "end_queue": plus_one["projected_end_queue"],
                          "delta_minutes": plus_one["eta_now_minutes"] - base["eta_now_minutes"]},
        "close_one": {"eta_now_minutes": minus_one["eta_now_minutes"],
                      "end_queue": minus_one["projected_end_queue"],
                      "delta_minutes": minus_one["eta_now_minutes"] - base["eta_now_minutes"]},
        "process_20pct_faster": {"eta_now_minutes": faster["eta_now_minutes"],
                                 "delta_minutes": faster["eta_now_minutes"] - base["eta_now_minutes"]},
        "arrival_surge_50pct": {"eta_now_minutes": surge["eta_now_minutes"],
                                "end_queue": surge["projected_end_queue"]},
    }


def capacity_plan(mandi_id: str, target_date: str | None = None) -> dict:
    """Tomorrow's plan from the historical curve: farmers, tonnage, peak, counters, staff, slots."""
    curve = _arrival_curve(mandi_id)
    snap = get_snapshot(mandi_id)
    proc = snap["avg_process_minutes"] or 6.0
    expected = sum(curve.values())
    peak_hour = max(curve, key=curve.get) if curve else 12
    peak_arrivals = curve.get(peak_hour, 10.0)
    needed_counters = max(1, int(peak_arrivals * proc / 60.0 + 0.999))
    avg_lot_kg = query_one(
        "SELECT AVG(quantity_kg) AS q FROM tickets WHERE mandi_id = ? AND slot_date = ?",
        (mandi_id, today_str()),
    )["q"] or 500.0
    return {
        "mandi_id": mandi_id,
        "for_date": target_date or "tomorrow",
        "expected_farmers": round(expected),
        "expected_quantity_mt": round(expected * avg_lot_kg / 1000.0, 1),
        "expected_peak_window": f"{max(8, peak_hour - 1):02d}:00-{min(17, peak_hour + 1):02d}:00",
        "peak_hour": peak_hour,
        "recommended_counters": needed_counters,
        "recommended_staff": needed_counters + max(1, needed_counters // 3),
        "recommended_slot_capacity": int(expected * 1.1),
        "basis": f"30-day arrival curve; avg lot {avg_lot_kg:.0f} kg; {proc:.0f} min/farmer processing",
    }


def bottleneck_heatmap(mandi_id: str) -> dict:
    snap = get_snapshot(mandi_id)
    stages = ["BOOKING_CREATED", "ARRIVAL_VERIFIED", "WEIGHING", "QUALITY_CHECK",
              "PROCUREMENT_APPROVED", "PAYMENT_COMPLETED"]
    counts = {s: 0 for s in stages}
    for q in snap["queue"]:
        key = q["status"]
        if key == "SLOT_BOOKED":
            counts["BOOKING_CREATED"] += 1
        elif key == "ARRIVED":
            counts["ARRIVAL_VERIFIED"] += 1
        elif key in ("WEIGHING",):
            counts["WEIGHING"] += 1
        elif key == "QUALITY_CHECK":
            counts["QUALITY_CHECK"] += 1
        elif key == "PAYMENT":
            counts["PAYMENT_COMPLETED"] += 1
    total = sum(counts.values()) or 1
    heat = []
    for s in stages:
        share = counts[s] / total
        level = "HIGH" if share >= 0.4 else "MEDIUM" if share >= 0.2 else "LOW"
        heat.append({"stage": s, "waiting": counts[s], "share_pct": round(share * 100), "level": level})
    top = max(heat, key=lambda h: (h["level"] == "HIGH", h["waiting"]))
    return {"mandi_id": mandi_id, "heatmap": heat,
            "primary_bottleneck": top["stage"] if top["waiting"] else None,
            "note": "Share of currently-waiting farmers held at each stage"}


def quantity_forecast(mandi_id: str) -> dict:
    rows = query_one(
        """
        SELECT SUM(quantity_kg) AS received,
               SUM(CASE WHEN status IN ('SLOT_BOOKED','ARRIVED') THEN quantity_kg ELSE 0 END) AS incoming
        FROM tickets WHERE mandi_id = ? AND slot_date = ?
          AND status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT','COMPLETED')
        """,
        (mandi_id, today_str()),
    )
    received = (rows["received"] or 0) / 1000.0
    incoming = (rows["incoming"] or 0) / 1000.0
    return {"mandi_id": mandi_id, "received_mt": round(received, 1),
            "expected_remaining_mt": round(incoming, 1),
            "expected_eod_mt": round(received + incoming, 1),
            "note": "Sum of booked lots; deployment: blend with season calendar"}
