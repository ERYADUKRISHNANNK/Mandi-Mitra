"""Database seeding: mandis, counters, staff users, synthetic history and a
live demo queue. Runs automatically on first startup."""

import random
from datetime import datetime, timedelta

from .db import execute, init_db, query_one
from .predictor import train

CROPS = ["Paddy", "Wheat", "Maize"]
LANGS = ["ml", "ml", "ml", "en", "hi", "ta"]
FIRST_NAMES = ["Rajan", "Meera", "Suresh", "Lakshmi", "Anil", "Devika", "Manoj",
               "Priya", "Vikram", "Sreeja", "Thomas", "Fathima", "Harish", "Nandini"]
LAST_NAMES = ["Kumar", "Menon", "Nair", "Pillai", "Reddy", "Shetty", "Varma", "Iyer"]

MANDIS = [
    {"id": "KL-KOCHI-01", "name": "Kochi Central Procurement Centre", "district": "Ernakulam", "lat": 9.9312, "lng": 76.2673},
    {"id": "KL-THRIS-02", "name": "Thrissur Mandi", "district": "Thrissur", "lat": 10.5276, "lng": 76.2144},
    {"id": "KL-PALAK-03", "name": "Palakkad Procurement Centre", "district": "Palakkad", "lat": 10.7867, "lng": 76.6548},
]


def seed_if_empty():
    init_db()
    if query_one("SELECT COUNT(*) AS n FROM mandis")["n"]:
        return

    # --- Mandis & counters -------------------------------------------------
    for m in MANDIS:
        execute(
            "INSERT INTO mandis (id, name, district, lat, lng, opens_at, closes_at)"
            " VALUES (?, ?, ?, ?, ?, '08:00', '17:00')",
            (m["id"], m["name"], m["district"], m["lat"], m["lng"]),
        )
        for i, ctype in enumerate(["WEIGHING", "WEIGHING", "QUALITY_CHECK"]):
            execute(
                "INSERT INTO counters (mandi_id, code, type, is_active) VALUES (?, ?, ?, 1)",
                (m["id"], f"C{i + 1}", ctype),
            )

    # --- Staff users --------------------------------------------------------
    from .security import hash_password
    execute(
        "INSERT INTO staff_users (username, password_hash, role, mandi_id, name) VALUES (?, ?, 'STAFF', ?, ?)",
        ("staff1", hash_password("staff123"), "KL-KOCHI-01", "Kochi Counter Staff"),
    )
    execute(
        "INSERT INTO staff_users (username, password_hash, role, mandi_id, name) VALUES (?, ?, 'ADMIN', NULL, ?)",
        ("admin", hash_password("admin123"), "District Officer"),
    )

    # --- 30 days of synthetic history (trains the prediction models) --------
    rng = random.Random(42)
    today = datetime.now()
    for m in MANDIS:
        for d in range(30, 0, -1):
            date = (today - timedelta(days=d)).strftime("%Y-%m-%d")
            weekday = (today - timedelta(days=d)).weekday()
            weekend_factor = 0.7 if weekday >= 5 else 1.0
            for hour in range(8, 17):
                base = 10 - abs(hour - 12)  # peak around midday
                arrivals = max(0, int(base * weekend_factor * rng.uniform(0.7, 1.3)))
                counters = rng.choice([2, 3, 3])
                processed = min(arrivals + rng.randint(-2, 2), counters * 10)
                avg_wait = round(max(2.0, (arrivals * 6.0) / max(1, counters)), 1)
                execute(
                    "INSERT INTO history_stats (mandi_id, date, hour, arrivals, processed, avg_wait_min, counters_active)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (m["id"], date, hour, arrivals, processed, avg_wait, counters),
                )

    train()


def add_demo_queue(mandi_id: str = "KL-KOCHI-01"):
    """Inserts a realistic mid-morning queue for the demo day."""
    rng = random.Random(7)
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    existing = query_one("SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ?", (mandi_id, date))
    if existing["n"]:
        return

    seq = 1000
    phone_pool = [f"9{rng.randint(100000000, 999999999)}" for _ in range(30)]

    def next_token():
        nonlocal seq
        seq += 1
        return f"MND-{seq}"

    # 2 completed procurements earlier today (gives the timeline + receipts real data)
    for i, status_offset in enumerate([(-150, "COMPLETED"), (-120, "COMPLETED")]):
        mins_ago, _ = status_offset
        phone = phone_pool[i]
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        crop = CROPS[i % 3]
        qty = rng.randint(400, 900)
        created = now + timedelta(minutes=mins_ago)
        arrived = created + timedelta(minutes=5)
        stage = arrived + timedelta(minutes=8)
        done = stage + timedelta(minutes=12)
        grade = "A" if i % 2 == 0 else "B"
        from .pricing import procurement_amount
        amount = procurement_amount(crop, grade, qty)
        execute(
            """
            INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg, slot_date, slot_time,
                lang, status, priority, stage_started_at, quality_grade, amount, payment_status,
                payment_submitted_at, payment_completed_at, checked_in_at, completed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '08:30', ?, 'COMPLETED', 0, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?)
            """,
            (next_token(), mandi_id, phone, name, crop, qty, date, rng.choice(LANGS),
             stage.isoformat(timespec="seconds"), grade, amount,
             done.isoformat(timespec="seconds"), done.isoformat(timespec="seconds"),
             arrived.isoformat(timespec="seconds"), done.isoformat(timespec="seconds"),
             created.isoformat(timespec="seconds")),
        )

    # 1 farmer currently being weighed, 1 at quality check
    serving = [
        ("WEIGHING", -12),
        ("QUALITY_CHECK", -20),
    ]
    for status, mins_ago in serving:
        phone = phone_pool[len(str(seq)) + 1]
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        crop = rng.choice(CROPS)
        qty = rng.randint(300, 800)
        arrived = now + timedelta(minutes=mins_ago)
        stage = arrived + timedelta(minutes=6)
        execute(
            """
            INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg, slot_date, slot_time,
                lang, status, priority, stage_started_at, checked_in_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (next_token(), mandi_id, phone, name, crop, qty, date,
             arrived.strftime("%H:%M"), rng.choice(LANGS), status,
             stage.isoformat(timespec="seconds"), arrived.isoformat(timespec="seconds"),
             arrived.isoformat(timespec="seconds")),
        )

    # 5 arrived + 4 booked-ahead queue
    for i in range(5):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        crop = rng.choice(CROPS)
        qty = rng.randint(200, 700)
        slot = (now + timedelta(minutes=10 * i + rng.randint(0, 9))).strftime("%H:%M")
        arrived_at = now - timedelta(minutes=rng.randint(5, 40)) if i < 4 else None
        status = "ARRIVED" if arrived_at else "SLOT_BOOKED"
        execute(
            """
            INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg, slot_date, slot_time,
                lang, status, priority, checked_in_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (next_token(), mandi_id, phone_pool[10 + i], name, crop, qty, date, slot,
             rng.choice(LANGS), status,
             arrived_at.isoformat(timespec="seconds") if arrived_at else None,
             (now - timedelta(minutes=60 + 5 * i)).isoformat(timespec="seconds")),
        )

    for i in range(4):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        crop = rng.choice(CROPS)
        qty = rng.randint(250, 600)
        slot = (now + timedelta(minutes=40 + 25 * i)).strftime("%H:%M")
        execute(
            """
            INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg, slot_date, slot_time,
                lang, status, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SLOT_BOOKED', 0, ?)
            """,
            (next_token(), mandi_id, phone_pool[20 + i], name, crop, qty, date, slot,
             rng.choice(LANGS),
             (now - timedelta(minutes=30 + 5 * i)).isoformat(timespec="seconds")),
        )
