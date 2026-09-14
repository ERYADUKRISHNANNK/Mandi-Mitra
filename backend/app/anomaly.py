"""AI-assisted anomaly / fraud detection (AI module 3).

Rule + statistics based flags raised for staff review — never automatic
accusations. Flags are derived from booking and event patterns:
  - duplicate/velocity booking from one phone
  - repeated no-show behaviour
  - abnormal stage processing times
  - queue position irregularities (out-of-order advancement)
  - suspiciously large quantities clustered on one phone
"""

from .db import now_iso, query, today_str

ACTIVE_STATUSES = "('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')"


def scan(mandi_id: str) -> dict:
    flags = []
    date = today_str()

    # 1. Booking velocity: too many active bookings from a single phone today.
    rows = query(
        f"""
        SELECT phone, COUNT(*) AS n, GROUP_CONCAT(token) AS tokens
        FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status IN {ACTIVE_STATUSES}
        GROUP BY phone HAVING n >= 3
        """,
        (mandi_id, date),
    )
    for r in rows:
        flags.append({
            "type": "BOOKING_VELOCITY",
            "severity": "HIGH" if r["n"] >= 5 else "MEDIUM",
            "phone": r["phone"],
            "detail": f"{r['n']} concurrent bookings from {r['phone']}: {r['tokens']}",
            "recommendation": "Verify identity at arrival counter before serving.",
        })

    # 2. Repeat no-show pattern.
    rows = query(
        """
        SELECT phone, COUNT(*) AS n FROM tickets
        WHERE mandi_id = ? AND status = 'NO_SHOW'
        GROUP BY phone HAVING n >= 2
        """,
        (mandi_id,),
    )
    for r in rows:
        flags.append({
            "type": "REPEAT_NO_SHOW",
            "severity": "MEDIUM",
            "phone": r["phone"],
            "detail": f"{r['n']} no-shows recorded for {r['phone']}",
            "recommendation": "Prioritise walk-in verification for this farmer.",
        })

    # 3. Abnormal processing time (stage open far too long = stuck/dereliction).
    rows = query(
        f"""
        SELECT token, status, stage_started_at,
               (julianday('now') - julianday(stage_started_at)) * 1440 AS mins
        FROM tickets
        WHERE mandi_id = ? AND slot_date = ? AND status IN ('WEIGHING','QUALITY_CHECK')
          AND stage_started_at IS NOT NULL
          AND (julianday('now') - julianday(stage_started_at)) * 1440 > 25
        """,
        (mandi_id, date),
    )
    for r in rows:
        flags.append({
            "type": "STUCK_STAGE",
            "severity": "HIGH",
            "token": r["token"],
            "detail": f"Token {r['token']} in {r['status']} for {int(r['mins'])} min",
            "recommendation": "Check counter status and reallocate if idle.",
        })

    # 4. Priority-jump irregularity: non-priority ticket ahead of earlier arrivals.
    rows = query(
        f"""
        SELECT a.token AS token, a.id AS aid, b.token AS btoken, b.id AS bid
        FROM tickets a JOIN tickets b
          ON a.mandi_id = b.mandi_id AND a.slot_date = b.slot_date
         AND a.priority > b.priority AND a.id > b.id
        WHERE a.mandi_id = ? AND a.slot_date = ?
          AND a.status IN {ACTIVE_STATUSES} AND b.status IN {ACTIVE_STATUSES}
        LIMIT 5
        """,
        (mandi_id, date),
    )
    for r in rows:
        flags.append({
            "type": "QUEUE_IRREGULARITY",
            "severity": "MEDIUM",
            "token": r["token"],
            "detail": f"Token {r['token']} listed ahead of earlier token {r['btoken']}",
            "recommendation": "Confirm the priority override was authorised.",
        })

    # 5. Quantity outliers: single phone with unusually large declared lots.
    rows = query(
        f"""
        SELECT phone, SUM(quantity_kg) AS total, COUNT(*) AS n
        FROM tickets WHERE mandi_id = ? AND slot_date = ? AND status IN {ACTIVE_STATUSES}
        GROUP BY phone HAVING total > 10000 OR n >= 2 AND total > 5000
        """,
        (mandi_id, date),
    )
    for r in rows:
        flags.append({
            "type": "QUANTITY_OUTLIER",
            "severity": "LOW",
            "phone": r["phone"],
            "detail": f"{int(r['total'])} kg declared across {r['n']} booking(s)",
            "recommendation": "Cross-check lot documents at weighing.",
        })

    return {
        "mandi_id": mandi_id,
        "scanned_at": now_iso(),
        "flag_count": len(flags),
        "flags": flags,
    }
