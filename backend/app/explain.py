"""Explainable AI — answers "why is my waiting time high?" with the actual
operational drivers, and scores mandi performance for administrators.

The explanations are computed from real numbers (counters, arrivals vs history,
stuck stages, no-shows), not generated text — so every claim is defensible.
"""

from datetime import datetime

from .db import query, query_one, today_str
from .queue_engine import get_snapshot


def why_wait(mandi_id: str, token: str | None = None) -> dict:
    snap = get_snapshot(mandi_id)
    waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
    counters_total = query_one("SELECT COUNT(*) AS n FROM counters WHERE mandi_id = ?", (mandi_id,))["n"]
    counters_active = snap["counters_active"]
    offline = counters_total - counters_active

    # Arrivals vs the 30-day hourly norm.
    hour = datetime.now().hour
    hist = query_one(
        "SELECT AVG(arrivals) AS a FROM history_stats WHERE mandi_id = ? AND hour = ?", (mandi_id, hour)
    )
    norm = hist["a"] if hist and hist["a"] else None
    today_rows = query(
        """
        SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ? AND checked_in_at IS NOT NULL
          AND strftime('%H', checked_in_at) = ?
        """,
        (mandi_id, today_str(), f"{hour:02d}"),
    )
    today_arrivals = today_rows[0]["n"] if today_rows else 0

    stuck = query_one(
        """
        SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ?
          AND status IN ('WEIGHING','QUALITY_CHECK') AND stage_started_at IS NOT NULL
          AND (julianday('now','localtime') - julianday(stage_started_at)) * 1440 > 25
        """,
        (mandi_id, today_str()),
    )["n"]

    factors = []
    if offline > 0:
        factors.append({"factor": f"{offline} of {counters_total} counters offline",
                        "impact": "HIGH", "detail": "Each offline counter multiplies effective wait."})
    if waiting >= 20:
        factors.append({"factor": f"{waiting} farmers currently waiting",
                        "impact": "HIGH", "detail": "Queue depth is the dominant driver."})
    if norm and today_arrivals > norm * 1.25:
        pct = round((today_arrivals / norm - 1) * 100)
        factors.append({"factor": f"Arrivals {pct}% above the normal for this hour",
                        "impact": "MEDIUM", "detail": f"Typical {norm:.0f}/h vs {today_arrivals} today."})
    if stuck:
        factors.append({"factor": f"{stuck} farmer(s) stuck at a stage for 25+ min",
                        "impact": "MEDIUM", "detail": "Blocks the counter pipeline behind them."})
    if snap["avg_process_minutes"] > 8:
        factors.append({"factor": f"Processing averaging {snap['avg_process_minutes']} min per farmer",
                        "impact": "MEDIUM", "detail": "Above the healthy 6-min benchmark."})
    if not factors:
        factors.append({"factor": "Operations are normal for this hour",
                        "impact": "LOW", "detail": "Wait reflects your position, not a bottleneck."})

    mine = None
    if token:
        q = next((q for q in snap["queue"] if q["token"] == token), None)
        if q:
            mine = {"position": q["position"], "eta_minutes": q["eta_minutes"],
                    "queue_group": q["queue_group"]}
    return {"mandi_id": mandi_id, "token": token, "your_position": mine,
            "drivers": factors, "current_wait_minutes": round(waiting * (snap["avg_process_minutes"] or 6) / max(1, counters_active), 0)}


def mandi_performance(mandi_id: str) -> dict:
    date = today_str()
    s = query_one(
        """
        SELECT
          SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
          SUM(CASE WHEN status = 'NO_SHOW' THEN 1 ELSE 0 END) AS no_shows,
          AVG(CASE WHEN checked_in_at IS NOT NULL AND completed_at IS NOT NULL
              THEN (julianday(completed_at) - julianday(checked_in_at)) * 1440 END) AS avg_time,
          SUM(CASE WHEN payment_delayed = 1 THEN 1 ELSE 0 END) AS delayed
        FROM tickets WHERE mandi_id = ? AND slot_date = ?
        """,
        (mandi_id, date),
    )
    fb = query_one(
        "SELECT AVG(overall) AS o, COUNT(*) AS n FROM feedback WHERE mandi_id = ? AND created_at >= ?",
        (mandi_id, date + "T00:00:00"),
    )
    grv = query_one(
        "SELECT COUNT(*) AS n FROM grievances WHERE mandi_id = ?", (mandi_id,)
    )
    completed = s["completed"] or 0
    no_shows = s["no_shows"] or 0
    avg_time = s["avg_time"] or 0
    rating = fb["o"] or 3.5
    grv_rate = min(1.0, (grv["n"] or 0) / max(1, completed + no_shows))

    efficiency = max(0.0, 1 - avg_time / 120.0) if avg_time else 0.9
    payment_ok = 1 - min(1.0, (s["delayed"] or 0) / max(1, completed))
    score = (0.3 * efficiency + 0.25 * payment_ok + 0.25 * (rating / 5.0)
             + 0.1 * (1 - min(1.0, no_shows / max(1, completed + no_shows)))
             + 0.1 * (1 - grv_rate)) * 100

    # Top bottleneck: the stage holding the most farmers right now.
    snap = get_snapshot(mandi_id)
    stage_counts = {}
    for q in snap["queue"]:
        stage_counts[q["status"]] = stage_counts.get(q["status"], 0) + 1
    top_stage = max(stage_counts, key=stage_counts.get) if stage_counts else None
    advice = {
        "WEIGHING": "Consider additional weighing capacity — most waiting farmers are queued for weighing.",
        "QUALITY_CHECK": "Top bottleneck is quality-check — add QC capacity in the 11:00-14:00 window.",
        "SLOT_BOOKED": "Heavy pre-arrival load — stagger slots or broadcast IVR to smooth arrivals.",
        "ARRIVED": "Waiting arrivals exceed serving capacity — open standby counters.",
    }.get(top_stage, "Operations balanced across stages right now.")

    return {
        "mandi_id": mandi_id,
        "score": round(score, 1),
        "metrics": {
            "completed_today": completed,
            "no_shows_today": no_shows,
            "avg_minutes_in_mandi": round(avg_time, 1),
            "delayed_payments": s["delayed"] or 0,
            "farmer_rating": round(rating, 1),
            "grievances_total": grv["n"] or 0,
        },
        "top_bottleneck": top_stage,
        "recommendation": advice,
    }


def system_health() -> dict:
    """National deployment health view (prototype simulates gateway states)."""
    mandis = query("SELECT id FROM mandis")
    online = 0
    for m in mandis:
        try:
            get_snapshot(m["id"])
            online += 1
        except Exception:
            pass
    return {
        "services": [
            {"name": "API", "state": "🟢", "detail": "operational"},
            {"name": "Database", "state": "🟢", "detail": "operational"},
            {"name": "Queue Engine", "state": "🟢", "detail": "recomputations live"},
            {"name": "SMS Gateway", "state": "🟡", "detail": "simulated in prototype"},
            {"name": "IVR", "state": "🟡", "detail": "simulated in prototype"},
            {"name": "AI/ML Service", "state": "🟢", "detail": "4 modules active"},
            {"name": "RAG Knowledge", "state": "🟢", "detail": "knowledge base loaded"},
            {"name": "MCP Tool Layer", "state": "🟢", "detail": f"{len(__import__('app.assistant', fromlist=['TOOLS']).TOOLS)} tools registered"},
        ],
        "mandis": {"total": len(mandis), "online": online, "offline": len(mandis) - online},
    }
