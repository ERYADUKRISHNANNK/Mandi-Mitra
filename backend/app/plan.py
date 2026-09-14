"""Wave-6 — AI Procurement Copilot.

Design principle: the farmer speaks naturally in their own language; the
backend does the intelligence. Nothing here exposes AI jargon to farmers —
the copilot returns ONE plan (where, when, leave-at, expected wait, value,
documents) with the reasoning attached for judges, not for farmers.

Modules:
  parse_intent       — multilingual NLU (crop, quantity, time, date)
  build_plan         — the "Where should I go?" best-procurement-plan engine
  departure_advice   — the "Don't come yet" / "Leave now" advisor
  transfer_offer     — proactive intelligent rebooking when load shifts
  transfer_booking   — execute the farmer-approved transfer (priority re-slot)
  network_brain      — national-level daily intelligence for administrators
"""

import re
from datetime import datetime, timedelta

from .db import execute, now_iso, query, query_one, today_str
from .discovery import discover, haversine_km
from .rates import estimated_value, rate_for

# --------------------------------------------------------------------------
# 1) Multilingual intent parsing
# --------------------------------------------------------------------------

CROP_WORDS = {
    "en": {"paddy": "Paddy", "rice": "Paddy", "nellu": "Paddy", "wheat": "Wheat",
           "godhumai": "Wheat", "maize": "Maize", "corn": "Maize", "cholam": "Maize"},
    "ml": {"നെല്ല്": "Paddy", "നെല്ല": "Paddy", "ഗോതമ്പ്": "Wheat", "ചോളം": "Maize"},
    "hi": {"धान": "Paddy", "चावल": "Paddy", "गेहूं": "Wheat", "गेहूँ": "Wheat", "मक्का": "Maize"},
    "ta": {"நெல்": "Paddy", "கோதுமை": "Wheat", "மக்காச்சோளம்": "Maize", "சோளம்": "Maize"},
}
BAG_WORDS = ["bag", "bags", "chattak", "സഞ്ചി", "സഞ്ചികൾ", "बोरी", "बोरियां", "பை", "பைகள்"]
KG_WORDS = ["kg", "kgs", "kilos", "kilogram", "കിലോ", "കിലോഗ്രാം", "किलो", "किलोग्राम", "கிலோ", "கிலோகிராம்"]
QTL_WORDS = ["quintal", "quintals", "ക്വിന്റൽ", "क्विंटल", "குயின்டால்"]
BAG_KG = 50.0  # standard procurement bag assumption (shown to the farmer)

DATE_WORDS = {
    "today": ["today", "ഇന്ന്", "आज", "இன்று"],
    "tomorrow": ["tomorrow", "നാളെ", "नाळെ", "कल", "நாளை"],
}
AFTERNOON_WORDS = ["afternoon", "noon", "ഉച്ച", "दोपहर", "மதியம்"]
EVENING_WORDS = ["evening", "വൈകുന്നേരം", "വൈകുന്നേരത്ത്", "शाम", "மாலை"]
MORNING_WORDS = ["morning", "രാവിലെ", "പ്രഭാതം", "सुबह", "காலை"]
NOW_WORDS = ["now", "ഇപ്പോൾ", "अभी", "இப்போது"]


def _all_crops() -> dict:
    merged: dict[str, str] = {}
    for d in CROP_WORDS.values():
        merged.update(d)
    return merged


def parse_intent(text: str, lang: str = "ml") -> dict:
    """Extract {crop, quantity_kg, hour, date_offset, found[]} from free text.
    Never throws — unknown pieces are simply reported as not found."""
    t = (text or "").lower()
    found = []

    # --- crop (search all languages regardless of UI lang) ---
    crop = next((c for w, c in _all_crops().items() if w in t), None)
    if crop:
        found.append("crop")

    # --- quantity: match a number DIRECTLY followed by its unit ---
    qty = None
    unit_patterns = [
        (BAG_WORDS, BAG_KG, "quantity_bags"),
        (KG_WORDS, 1.0, "quantity"),
        (QTL_WORDS, 100.0, "quantity"),
    ]
    for words, factor, tag in unit_patterns:
        for w in words:
            m = re.search(r"(\d+(?:\.\d+)?)\s*" + re.escape(w), t)
            if m:
                qty = float(m.group(1)) * factor
                found.append(tag)
                break
        if qty is not None:
            break
    if qty is None:  # bare number with no unit nearby -> treat as kg
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilos)?\b", t)
        if m and "time" not in found:
            qty = float(m.group(1))
            found.append("quantity")

    # --- date ---
    date_offset = 0
    if any(w in t for w in DATE_WORDS["tomorrow"]):
        date_offset = 1
        found.append("date")
    elif any(w in t for w in DATE_WORDS["today"]):
        found.append("date")

    # --- hour ---
    hour = None
    hm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", t)
    if hm:
        h = int(hm.group(1))
        minute = int(hm.group(2) or 0)
        suffix = hm.group(3)
        if suffix and "p" in suffix and h < 12:
            h += 12
        if suffix and "a" in suffix and h == 12:
            h = 0
        if not suffix and h in (1, 2, 3, 4, 5, 6) and not any(w in t for w in MORNING_WORDS):
            h += 12  # "3 മണിക്ക്" / "3 बजे" — farmers mean the afternoon
        if 6 <= h <= 21:
            hour = h + minute / 60.0
            found.append("time")
    if hour is None:
        if any(w in t for w in AFTERNOON_WORDS):
            hour, _ = 13.0, found.append("time")
        elif any(w in t for w in EVENING_WORDS):
            hour, _ = 16.0, found.append("time")
        elif any(w in t for w in MORNING_WORDS):
            hour, _ = 9.0, found.append("time")

    return {"crop": crop, "quantity_kg": qty, "hour": hour, "date_offset": date_offset,
            "lang": lang, "found": sorted(set(found))}


# --------------------------------------------------------------------------
# 2) The best-procurement-plan engine
# --------------------------------------------------------------------------

DOCS_FALLBACK = ("Land record / passbook, ID proof, bank passbook and the slot "
                 "confirmation (SMS or app). Verify with your centre before travel.")

SAVINGS = {
    "ml": " — {name}-നെ അപേക്ഷിച്ച് ഏകദേശം {saved} ലാഭം.",
    "en": " That saves about {saved} compared with {name}.",
    "hi": " — {name} की तुलना में लगभग {saved} बचत।",
    "ta": " — {name} ஒப்பிடும்போது சுமார் {saved} சேமிப்பு.",
}


def _fmt_hm(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes} min"


HEADLINES = {
    "ml": "{name}-ൽ പോകൂ. {leave} ന് വീട്ടിൽ നിന്ന് ഇറങ്ങുക — യാത്ര {travel} മിനിറ്റ്, കാത്തിരിപ്പ് ഏകദേശം {wait} മിനിറ്റ്.",
    "en": "Go to {name}. Leave home at {leave} — {travel} min travel, expected waiting about {wait} min.",
    "hi": "{name} जाएं। {leave} बजे घर से निकलें — यात्रा {travel} मिनट, अपेक्षित प्रतीक्षा लगभग {wait} मिनट।",
    "ta": "{name} செல்லுங்கள். {leave} க்கு வீட்டை விட்டு கிளம்புங்கள் — பயணம் {travel} நிமிடம், காத்திருப்பு சுமார் {wait} நிமிடம்.",
}


def build_plan(lat: float | None, lng: float | None, crop: str | None,
               quantity_kg: float | None, lang: str = "ml",
               hour: float | None = None) -> dict:
    """ONE recommendation: where to go, when to leave, what to expect."""
    centres = discover(lat, lng, crop, quantity_kg or 0)
    open_centres = [c for c in centres if c["status"] == "OPEN"]
    if not open_centres:
        return {"ok": False, "reply": "No centres are open right now. Please try again shortly.",
                "parse": {"crop": crop, "quantity_kg": quantity_kg, "hour": hour}}

    ranked = sorted(open_centres, key=lambda c: c["total_journey_minutes"])
    best = ranked[0]
    now = datetime.now()

    # Target arrival: honour the farmer's requested hour if it's still ahead,
    # otherwise now + travel + a small buffer.
    if hour is not None:
        arrival = now.replace(hour=int(hour), minute=int(round((hour % 1) * 60)), second=0, microsecond=0)
        if arrival < now:
            arrival = now + timedelta(minutes=best["travel_minutes"] + 20)
    else:
        arrival = now + timedelta(minutes=best["travel_minutes"] + 20)
    leave_at = arrival - timedelta(minutes=best["travel_minutes"] + 10)
    if leave_at < now:
        leave_at = now

    # Savings vs the slowest open alternative (the farmer-facing number).
    slowest = max(ranked, key=lambda c: c["total_journey_minutes"])
    saved_min = max(0, int(slowest["total_journey_minutes"] - best["total_journey_minutes"]))

    rate = rate_for(crop) if crop else None
    docs = DOCS_FALLBACK
    try:
        from .assistant import rag_search
        hits = rag_search("documents required farmer procurement")
        if hits:
            docs = hits[0]["content"][:180]
    except Exception:
        pass

    completeness = (0.45 if crop else 0.0) + (0.3 if quantity_kg else 0.0) + (0.25 if hour is not None else 0.0)
    confidence = round(0.55 + 0.4 * completeness, 2)

    tmpl = HEADLINES.get(lang, HEADLINES["en"])
    reply = tmpl.format(name=best["name"], leave=leave_at.strftime("%I:%M %p").lstrip("0"),
                        travel=int(best["travel_minutes"]), wait=int(best["queue_wait_minutes"]))
    requested_passed = hour is not None and arrival < now + timedelta(minutes=1)
    if saved_min >= 20:
        reply += SAVINGS.get(lang, SAVINGS["en"]).format(name=slowest["name"], saved=_fmt_hm(saved_min))
    if requested_passed:
        reply += " (Your requested time has already passed today, so this is the earliest possible plan.)"

    return {
        "ok": True,
        "reply": reply,
        "plan": {
            "mandi_id": best["mandi_id"], "name": best["name"], "district": best["district"],
            "distance_km": best["distance_km"], "travel_minutes": best["travel_minutes"],
            "leave_at": leave_at.isoformat(timespec="minutes"),
            "leave_at_hhmm": leave_at.strftime("%H:%M"),
            "arrival_at": arrival.isoformat(timespec="minutes"),
            "queue_length": best["queue_length"],
            "expected_wait_minutes": best["queue_wait_minutes"],
            "total_journey_minutes": best["total_journey_minutes"],
            "counters_active": best["counters_active"],
            "rate": rate, "estimated_value": estimated_value(crop, quantity_kg) if crop and quantity_kg else None,
            "documents": docs,
            "saved_vs_worst_minutes": saved_min,
        },
        "alternatives": [
            {"mandi_id": c["mandi_id"], "name": c["name"], "queue_length": c["queue_length"],
             "total_journey_minutes": c["total_journey_minutes"]}
            for c in ranked[1:3]
        ],
        "assumptions": [],  # filled by the route when bags were used (50 kg each)
        "confidence": confidence,
        "parse": {"crop": crop, "quantity_kg": quantity_kg, "hour": hour},
    }


# --------------------------------------------------------------------------
# 3) "Don't come yet" — departure advisor for a booked farmer
# --------------------------------------------------------------------------

def departure_advice(mandi_id: str, token: str) -> dict:
    snap = _snap(mandi_id)
    item = next((q for q in snap["queue"] if q["token"] == token), None)
    if not item:
        return {"error": "not_in_queue"}
    if item["status"] != "SLOT_BOOKED":
        return {"advice": "come", "message": "You are already at the centre or being served.",
                "advised_departure": None}
    proc = snap["avg_process_minutes"] or 6.0
    counters = max(1, snap["counters_active"] or 1)
    ahead = [q for q in snap["queue"] if q["queue_group"] == "WAITING"
             and (q["position"] or 0) < (item["position"] or 0)]
    wait_min = len(ahead) * proc / counters
    now = datetime.now()
    depart = now + timedelta(minutes=max(0.0, wait_min - 10))  # 10-min buffer
    if wait_min > 45:
        advice, msg = "wait", (f"Don't come yet — start at about {depart.strftime('%I:%M %p').lstrip('0')}. "
                               f"Your turn is roughly {int(wait_min)} minutes away.")
    elif wait_min > 20:
        advice, msg = "soon", (f"Get ready — start within {max(5, int(wait_min - 10))} minutes "
                               f"(around {depart.strftime('%I:%M %p').lstrip('0')}).")
    else:
        advice, msg = "leave", "Leave now — your turn is approaching."
    return {"token": token, "advice": advice, "expected_wait_minutes": int(wait_min),
            "position": item.get("position"), "eta_minutes": item.get("eta_minutes"),
            "advised_departure": depart.isoformat(timespec="minutes"),
            "advised_departure_hhmm": depart.strftime("%H:%M"), "message": msg,
            "note": "Recomputed live from arrivals and processing rate — not a fixed slot time."}


def _snap(mandi_id: str) -> dict:
    from .queue_engine import get_snapshot
    return get_snapshot(mandi_id)


# --------------------------------------------------------------------------
# 4) Intelligent rebooking — proactive transfer offer + execution
# --------------------------------------------------------------------------

def transfer_offer(mandi_id: str, token: str) -> dict:
    t = query_one("SELECT * FROM tickets WHERE token = ?", (token,))
    if not t:
        return {"error": "unknown_token"}
    snap = _snap(mandi_id)
    proc = snap["avg_process_minutes"] or 6.0
    counters = max(1, snap["counters_active"] or 1)
    mine = next((q for q in snap["queue"] if q["token"] == token), None)
    if not mine or mine["status"] not in ("SLOT_BOOKED", "ARRIVED"):
        return {"offer": None, "reason": "only offered before processing begins"}
    current_wait = max(0, (mine["position"] or 0)) * proc / counters

    mandi = query_one("SELECT * FROM mandis WHERE id = ?", (mandi_id,))
    alts = []
    for c in discover(mandi["lat"], mandi["lng"], t["crop"], t["quantity_kg"]):
        if c["mandi_id"] == mandi_id or c["status"] != "OPEN":
            continue
        delta = c["queue_wait_minutes"] + c["travel_minutes"] - current_wait
        alts.append({**{k: c[k] for k in ("mandi_id", "name", "queue_length", "travel_minutes",
                                          "queue_wait_minutes", "distance_km", "total_journey_minutes")},
                     "wait_advantage_minutes": round(current_wait - c["queue_wait_minutes"], 0)})
    alts.sort(key=lambda a: -a["wait_advantage_minutes"])
    best = alts[0] if alts else None
    offer = best and best["wait_advantage_minutes"] >= 25
    return {"token": token, "current_wait_minutes": round(current_wait, 0),
            "offer": offer, "recommended": best if offer else None,
            "alternatives": alts[:3],
            "note": "Farmer decides — the system only suggests; transfer requires an explicit yes."}


def transfer_booking(token: str, to_mandi_id: str) -> dict:
    """Farmer-approved transfer: old ticket is cancelled, a new priority token
    is minted at the target centre (transfers precede same-day walk-ins)."""
    t = query_one("SELECT * FROM tickets WHERE token = ?", (token,))
    if not t:
        raise ValueError("unknown token")
    if t["status"] not in ("SLOT_BOOKED", "ARRIVED"):
        raise ValueError("transfer only possible before weighing begins")
    target = query_one("SELECT * FROM mandis WHERE id = ?", (to_mandi_id,))
    if not target:
        raise ValueError("unknown target centre")

    from .routes_farmer import next_token
    new_token = next_token(to_mandi_id)
    now = now_iso()
    execute(
        """INSERT INTO tickets (token, mandi_id, phone, farmer_name, crop, quantity_kg,
             slot_date, slot_time, lang, status, priority, priority_flag, vehicle_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SLOT_BOOKED', -1, 'TRANSFER', ?, ?)""",
        (new_token, to_mandi_id, t["phone"], t["farmer_name"], t["crop"], t["quantity_kg"],
         today_str(), datetime.now().strftime("%H:%M"), t["lang"], t["vehicle_type"], now),
    )
    execute("UPDATE tickets SET status = 'CANCELLED' WHERE id = ?", (t["id"],))
    from .audit import log_event
    from .notify import send_sms
    log_event(to_mandi_id, "SYSTEM", "TRANSFER_BOOKING", {"from": token, "to": new_token}, None)
    send_sms(t["phone"], t["lang"], "BOOKING_CONFIRMED", {"token": new_token}, None)
    from .queue_engine import recompute_mandi
    recompute_mandi(to_mandi_id)
    recompute_mandi(t["mandi_id"])
    nt = query_one("SELECT id FROM tickets WHERE token = ?", (new_token,))
    return {"ok": True, "old_token": token, "new_token": new_token,
            "to_mandi": target["name"], "priority": "transfer — served ahead of same-day walk-ins"}


# --------------------------------------------------------------------------
# 5) National Mandi Brain — government-level daily intelligence
# --------------------------------------------------------------------------

def network_brain() -> dict:
    from .twin import capacity_plan, quantity_forecast
    mandis = []
    actions: list[str] = []
    overloaded = underutilized = payment_hotspots = 0
    for m in query("SELECT * FROM mandis"):
        snap = _snap(m["id"])
        waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
        plan = capacity_plan(m["id"])
        qf = quantity_forecast(m["id"])
        delayed = query_one(
            "SELECT COUNT(*) AS n FROM tickets WHERE mandi_id = ? AND slot_date = ? AND payment_delayed = 1",
            (m["id"], today_str()))["n"]
        flags = []
        if plan["expected_farmers"] >= 60 and plan["recommended_counters"] > snap["counters_active"]:
            overloaded += 1
            flags.append(f"tomorrow overloaded: {plan['expected_farmers']} farmers expected, "
                         f"{plan['recommended_counters']} counters needed")
            actions.append(f"{m['name']}: schedule {plan['recommended_counters']} counters by "
                           f"{plan['expected_peak_window']} tomorrow")
        if waiting <= 5 and snap["counters_active"] >= 3:
            underutilized += 1
            flags.append("underutilized: idle counters with almost no queue")
            actions.append(f"{m['name']}: eligible to absorb diverted farmers from congested centres")
        if delayed > 0:
            payment_hotspots += 1
            flags.append(f"payment hotspot: {delayed} delayed payments")
            actions.append(f"{m['name']}: prioritise {delayed} delayed payment case(s) today")
        mandis.append({
            "mandi_id": m["id"], "name": m["name"], "district": m["district"],
            "waiting_now": waiting, "counters_active": snap["counters_active"],
            "expected_tomorrow": plan["expected_farmers"], "peak_window_tomorrow": plan["expected_peak_window"],
            "expected_eod_mt": qf["expected_eod_mt"], "delayed_payments": delayed,
            "flags": flags, "level": "HIGH" if waiting >= 25 else "MODERATE" if waiting >= 10 else "LOW",
        })
    mandis.sort(key=lambda x: -x["waiting_now"])
    return {
        "mandis": mandis,
        "summary": {"monitored": len(mandis), "overloaded_tomorrow": overloaded,
                    "underutilized": underutilized, "payment_hotspots": payment_hotspots},
        "actions": actions[:8],
        "note": "AI-assisted network intelligence for administrators — recommendations, not automated decisions.",
    }
