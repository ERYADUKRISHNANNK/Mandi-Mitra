"""AI module 2 — congestion forecast.

Predicts arrivals per hour for the rest of the day using historical hourly
statistics blended with today's live arrival rate. Produces a Low / Moderate /
High label per hour for the staff dashboard and command centre.
"""

from datetime import datetime

from .db import query, today_str


def _history_profile(mandi_id: str) -> dict[int, float]:
    """Average arrivals per hour-of-day across history."""
    rows = query(
        "SELECT hour, AVG(arrivals) AS a FROM history_stats WHERE mandi_id = ? GROUP BY hour",
        (mandi_id,),
    )
    return {r["hour"]: float(r["a"]) for r in rows}


def _live_arrival_rate(mandi_id: str) -> float | None:
    """Arrivals per hour so far today (None if the day just started)."""
    rows = query(
        """
        SELECT COUNT(*) AS n, MIN(checked_in_at) AS first_arrival
        FROM tickets WHERE mandi_id = ? AND slot_date = ? AND checked_in_at IS NOT NULL
        """,
        (mandi_id, today_str()),
    )
    r = rows[0] if rows else None
    if not r or not r["first_arrival"]:
        return None
    try:
        first = datetime.fromisoformat(r["first_arrival"])
        elapsed_h = max(0.25, (datetime.now() - first).total_seconds() / 3600.0)
        return r["n"] / elapsed_h
    except Exception:
        return None


def forecast(mandi_id: str, hours_ahead: int = 8) -> dict:
    """Hourly congestion forecast for the remainder of today."""
    now = datetime.now()
    start_hour = now.hour
    profile = _history_profile(mandi_id)
    live_rate = _live_arrival_rate(mandi_id)
    today_counts = {
        int(r["hour"]): r["n"]
        for r in query(
            """
            SELECT strftime('%H', checked_in_at) AS hour, COUNT(*) AS n
            FROM tickets WHERE mandi_id = ? AND slot_date = ? AND checked_in_at IS NOT NULL
            GROUP BY hour
            """,
            (mandi_id, today_str()),
        )
    }

    hourly = []
    for i in range(hours_ahead):
        hour = (start_hour + i) % 24
        hist = profile.get(hour, 0.0)
        live_today = float(today_counts.get(hour, 0) if hour <= now.hour else 0)
        # Blend: live partial counts dominate recent hours; history fills gaps.
        if hour < now.hour and live_today > 0:
            expected = live_today
        elif live_rate is not None and i <= 2:
            expected = round(0.6 * live_rate + 0.4 * hist, 1)
        else:
            expected = round(hist if hist > 0 else live_rate or 0.0, 1)

        if expected >= 14:
            level, label = "HIGH", "High"
        elif expected >= 8:
            level, label = "MODERATE", "Moderate"
        else:
            level, label = "LOW", "Low"

        hourly.append(
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "expected_arrivals": expected,
                "level": level,
                "level_label": label,
            }
        )
    return {"mandi_id": mandi_id, "generated_at": datetime.now().isoformat(timespec="seconds"), "hours": hourly}
