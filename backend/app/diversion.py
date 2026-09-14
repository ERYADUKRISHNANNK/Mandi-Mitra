"""Smart diversion — mandi load balancing.

When a farmer's chosen centre is congested, recommends a nearby centre with a
shorter expected wait, trading off live queue depth, counter capacity and road
distance (distance data is static in the prototype; deployment would use the
Maps API). Presented as an optional suggestion — farmers decide, in line with
procurement rules.
"""

from .db import query, query_one
from .queue_engine import get_snapshot

# Road distances (km) between prototype mandis (static reference data).
DISTANCE_KM = {
    ("KL-KOCHI-01", "KL-THRIS-02"): 82.0,
    ("KL-KOCHI-01", "KL-PALAK-03"): 135.0,
    ("KL-THRIS-02", "KL-PALAK-03"): 54.0,
}

FUEL_COST_PER_KM = 4.5  # ₹/km round-trip proxy for the advice text


def _pair_distance(a: str, b: str) -> float:
    return DISTANCE_KM.get((a, b), DISTANCE_KM.get((b, a), 999.0))


def _waiting(mandi_id: str) -> int:
    snap = get_snapshot(mandi_id)
    return sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")


def recommend_diversion(mandi_id: str) -> dict:
    home_waiting = _waiting(mandi_id)
    counters = query_one(
        "SELECT COUNT(*) AS n FROM counters WHERE mandi_id = ? AND is_active = 1", (mandi_id,)
    )["n"] or 1
    home_load_ratio = home_waiting / counters

    alternatives = []
    for m in query("SELECT id, name, district, lat, lng FROM mandis WHERE id != ?", (mandi_id,)):
        mid = m["id"]
        waiting = _waiting(mid)
        n_counters = query_one(
            "SELECT COUNT(*) AS n FROM counters WHERE mandi_id = ? AND is_active = 1", (mid,)
        )["n"] or 1
        load_ratio = waiting / n_counters
        distance = _pair_distance(mandi_id, mid)
        # Better only if meaningfully less crowded (>=30% lower load ratio)
        # and the detour doesn't wipe out the saved wait.
        if load_ratio < home_load_ratio * 0.7:
            saved_min = max(0.0, (home_load_ratio - load_ratio) * 6.0)
            drive_min = distance * 1.2  # ~50 km/h average
            worth_it = saved_min > 20 and saved_min > drive_min
            alternatives.append({
                "mandi_id": mid,
                "name": m["name"],
                "district": m["district"],
                "queue_length": waiting,
                "counters_active": n_counters,
                "distance_km": distance,
                "estimated_wait_min": round(load_ratio * 6.0, 0),
                "home_estimated_wait_min": round(home_load_ratio * 6.0, 0),
                "travel_minutes": round(drive_min, 0),
                "detour_cost_rs": round(distance * 2 * FUEL_COST_PER_KM, 0),
                "worth_it": bool(worth_it),
            })

    alternatives.sort(key=lambda a: (not a["worth_it"], a["queue_length"]))
    best = alternatives[0] if alternatives and alternatives[0]["worth_it"] else None
    return {
        "mandi_id": mandi_id,
        "home_queue_length": home_waiting,
        "home_status": "HIGH" if home_waiting >= 25 else "MODERATE" if home_waiting >= 10 else "LOW",
        "recommendation": best,
        "alternatives": alternatives,
        "note": "Suggestion only — farmers decide based on procurement rules and travel feasibility.",
    }
