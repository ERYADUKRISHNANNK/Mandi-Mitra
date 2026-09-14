"""Layer 2 — mandi discovery, experience ratings and Best-Mandi-For-Me AI.

For the prototype, three Kerala centres stand in for the national network; the
engine is distance-capable: given any farmer lat/lng it ranks every centre by
total journey time (travel + queue + processing) rather than raw distance, and
explains its ranking.
"""

import math
from datetime import datetime

from .db import query, query_one, today_str
from .queue_engine import get_snapshot
from .rates import rate_for, estimated_value
from .config import settings

AVG_SPEED_KMPH = 35.0
PROC_PROCESS_MIN = 20  # weighing + QC + paperwork for the farmer's own lot


def haversine_km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (0.5 - math.cos((lng2 - lng1) * p) / 2))
    return 12742 * math.asin(math.sqrt(a))


def mandi_rating(mandi_id: str) -> dict:
    rows = query(
        """
        SELECT AVG(waiting) AS w, AVG(staff) AS s, AVG(queue_mgmt) AS q, AVG(info) AS i,
               AVG(payment) AS p, AVG(facilities) AS f, AVG(overall) AS o, COUNT(*) AS n
        FROM feedback WHERE mandi_id = ?
        """,
        (mandi_id,),
    )
    r = rows[0] if rows else None
    if not r or not r["n"]:
        return {"score": None, "count": 0, "breakdown": {}}
    return {
        "score": round(r["o"], 1),
        "count": r["n"],
        "breakdown": {
            "waiting": round(r["w"], 1), "staff": round(r["s"], 1),
            "queue_management": round(r["q"], 1), "information": round(r["i"], 1),
            "payment": round(r["p"], 1), "facilities": round(r["f"], 1),
        },
    }


def _status_of(mandi_id: str) -> dict:
    row = query_one("SELECT status, note, updated_at FROM mandi_status WHERE mandi_id = ?", (mandi_id,))
    if row:
        return {"status": row["status"], "note": row["note"], "updated_at": row["updated_at"]}
    return {"status": "OPEN", "note": None, "updated_at": None}


def discover(lat: float | None = None, lng: float | None = None,
             crop: str | None = None, quantity_kg: float = 0, pin: str | None = None) -> list[dict]:
    centres = []
    now = datetime.now()
    for m in query("SELECT * FROM mandis"):
        snap = get_snapshot(m["id"])
        waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
        counters = snap["counters_active"] or 1
        queue_wait = waiting * (snap["avg_process_minutes"] or 6.0) / counters
        travel_min, distance_km = (0.0, 0.0)
        if lat is not None and lng is not None:
            distance_km = haversine_km(lat, lng, m["lat"], m["lng"])
            travel_min = distance_km / AVG_SPEED_KMPH * 60.0
        total = travel_min + queue_wait + PROC_PROCESS_MIN
        rate = rate_for(crop) if crop else None
        status = _status_of(m["id"])
        rating = mandi_rating(m["id"])
        centres.append({
            "mandi_id": m["id"], "name": m["name"], "district": m["district"],
            "state": m["state"],
            "lat": m["lat"], "lng": m["lng"],
            "status": status["status"], "status_note": status["note"],
            "distance_km": round(distance_km, 1),
            "travel_minutes": round(travel_min, 0),
            "queue_length": waiting,
            "queue_wait_minutes": round(queue_wait, 0),
            "counters_active": counters,
            "processed_today": snap["processed_today"],
            "proc_process_minutes": PROC_PROCESS_MIN,
            "total_journey_minutes": round(total, 0),
            "available_slots": max(0, 40 - waiting),
            "rate": rate,
            "estimated_value": estimated_value(crop, quantity_kg) if crop and quantity_kg else None,
            "rating": rating,
        })
    centres.sort(key=lambda c: c["total_journey_minutes"])
    return centres


def best_for_me(lat, lng, crop: str, quantity_kg: float) -> dict:
    centres = discover(lat, lng, crop, quantity_kg)
    open_centres = [c for c in centres if c["status"] == "OPEN"]

    def score(c):
        s = 100.0
        s -= c["total_journey_minutes"] * 0.6           # time dominates
        s += (c["rating"]["score"] or 3.5) * 4          # reputation
        s += min(10, c["available_slots"] / 3)          # availability
        if c["queue_wait_minutes"] > 60:
            s -= 15
        return s

    ranked = sorted(open_centres or centres, key=score, reverse=True)
    best = ranked[0] if ranked else None
    return {
        "crop": crop,
        "quantity_kg": quantity_kg,
        "recommended": best,
        "why": [
            f"Shortest total journey: {best['total_journey_minutes']} min "
            f"({best['travel_minutes']}m travel + {best['queue_wait_minutes']}m queue + "
            f"{best['proc_process_minutes']}m processing)" if best else "No open centres",
            f"Queue just {best['queue_length']} farmers at {best['counters_active']} counters" if best else "",
            f"Farmer rating {best['rating']['score'] or '—'}/5 from {best['rating']['count']} feedbacks" if best else "",
        ] if best else [],
        "alternatives": ranked[1:4],
        "eligibility_note": "Subject to state procurement rules on inter-centre movement.",
    }
