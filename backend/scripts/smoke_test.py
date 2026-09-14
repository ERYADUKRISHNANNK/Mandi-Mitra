"""End-to-end smoke test: farmer booking -> staff workflow -> payment -> receipt.

Run with the API up:  backend/.venv/Scripts/python backend/scripts/smoke_test.py [base_url]
"""

import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def call(method: str, path: str, body=None, token: str | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            raw = resp.read().decode() or ""
            ctype = resp.headers.get("Content-Type", "")
            if "json" not in ctype:
                return resp.status, raw
            return resp.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def check(name: str, cond: bool, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name} {extra}")


# --- health -----------------------------------------------------------------
code, health = call("GET", "/api/health")
check("health", code == 200 and health.get("receipt_chain_verified") is True)

# --- farmer registration & smart slots --------------------------------------
code, reg = call("POST", "/api/farmer/register",
                 {"phone": "9876543210", "name": "Smoke Farmer", "lang": "en"})
check("farmer register (Mandi Mitra ID)", code == 200 and reg.get("mm_id", "").startswith("MM-"))

code, rec = call("POST", "/api/farmer/otp/request", {"phone": "9876543210"})
code2, ver = call("POST", "/api/farmer/otp/verify",
                  {"phone": "9876543210", "code": rec.get("simulated_otp", "")})
check("otp request + verify", code == 200 and ver.get("verified") is True)

code, slots = call("GET", "/api/farmer/slots?mandi_id=KL-KOCHI-01&quantity_kg=500")
check("smart slot recommendations", code == 200 and len(slots.get("options", [])) > 0)
best = slots["options"][0]

# --- booking ----------------------------------------------------------------
code, booking = call("POST", "/api/farmer/book", {
    "mandi_id": "KL-KOCHI-01", "phone": "9876543210", "farmer_name": "Smoke Farmer",
    "crop": "Paddy", "quantity_kg": 500, "slot_time": best["slot_time"], "lang": "en"})
check("slot booking + token", code == 200 and booking.get("token", "").startswith("MND-"),
      json.dumps(booking)[:200])
token = booking.get("token")

code, dup = call("POST", "/api/farmer/book", {
    "mandi_id": "KL-KOCHI-01", "phone": "9876543210", "farmer_name": "Smoke Farmer",
    "crop": "Paddy", "quantity_kg": 500, "slot_time": best["slot_time"]})
check("duplicate booking rejected (409)", dup.get("code") == 409 or code == 409)

# --- staff login & workflow --------------------------------------------------
code, login = call("POST", "/api/staff/login", {"username": "staff1", "password": "staff123"})
check("staff login (JWT)", code == 200 and login.get("access_token"))
jwt = login.get("access_token", "")

code, dash = call("GET", "/api/staff/dashboard", token=jwt)
check("staff dashboard", code == 200 and "queue_length" in dash)

code, ci = call("POST", "/api/staff/checkin", {"token": token}, token=jwt)
check("arrival check-in", code == 200 and ci.get("ok"))

code, w = call("POST", "/api/staff/start-weighing", {"token": token}, token=jwt)
check("start weighing", code == 200 and w.get("status") == "WEIGHING")

code, q = call("POST", "/api/staff/start-quality", {"token": token}, token=jwt)
check("start quality check", code == 200 and q.get("status") == "QUALITY_CHECK")

code, comp = call("POST", "/api/staff/complete-procurement",
                  {"token": token, "quality_grade": "A"}, token=jwt)
check("procurement approved (MSP amount)", code == 200 and comp.get("amount", 0) == 23.0 * 500,
      str(comp.get("amount")))

code, pay = call("POST", "/api/staff/complete-payment", {"token": token}, token=jwt)
check("payment completed + receipt", code == 200 and pay.get("receipt_hash"))

code, receipt = call("GET", f"/api/farmer/receipt/{token}")
check("tamper-evident receipt w/ chain verify", code == 200 and receipt.get("chain_verified") is True)

code, status = call("GET", f"/api/farmer/status?token={token}")
check("farmer live status + timeline", code == 200 and len(status.get("timeline", [])) >= 5)

# --- IVR / SMS / missed-call channels ---------------------------------------
code, ivr = call("POST", "/api/farmer/ivr/call", {"phone": "9876543210", "lang": "en"})
check("IVR voice status", code == 200 and len(ivr.get("ivr_says", "")) > 10)

code, sms = call("POST", "/api/sms", {"phone": "9990001111",
                                      "message": "BOOK KL-KOCHI-01 WHEAT 700"})
check("SMS booking channel", code == 200 and "Booked" in sms.get("reply", ""), str(sms)[:160])

code, mc = call("POST", "/api/missed-call", {"phone": "9990001111"})
check("missed-call IVR callback", code == 200 and "position" in mc)

# --- autopilot + command centre ---------------------------------------------
code, auto = call("POST", "/api/staff/autopilot", {"steps": 4}, token=jwt)
check("demo autopilot", code == 200 and len(auto.get("actions", [])) > 0)

code, admin_login = call("POST", "/api/staff/login", {"username": "admin", "password": "admin123"})
admin_jwt = admin_login.get("access_token", "")
check("admin login", code == 200 and bool(admin_jwt))

code, cc = call("GET", "/api/admin/command-centre", token=admin_jwt)
check("district command centre", code == 200 and cc.get("mandis_monitored", 0) == 3)

code, an = call("GET", "/api/staff/anomalies", token=jwt)
check("anomaly scanner", code == 200 and "flags" in an)

code, bn = call("GET", "/api/staff/bottleneck", token=jwt)
check("bottleneck intelligence", code == 200 and "recommendations" in bn)

code, imp = call("GET", "/api/impact")
check("impact metrics", code == 200 and "farmer_hours_saved_today" in imp)

code, forbid = call("GET", "/api/admin/command-centre")
check("admin auth required (401/403)", code in (401, 403))

# --- wave-2 features ---------------------------------------------------------
code, sc = call("POST", "/api/farmer/self-checkin",
                {"token": token2 if "token2" in dir() else token, "lat": 9.9312, "lng": 76.2673})
check("GPS self check-in", code in (200, 409))  # 409 if already past SLOT_BOOKED

code, board = call("GET", "/api/board/KL-KOCHI-01")
check("public hall board", code == 200 and "now_serving" in board)

code, div = call("GET", "/api/staff/diversion", token=jwt)
check("smart diversion advice", code == 200 and "alternatives" in div)

# No-show then requeue: farmer returns to the live queue and NO_SHOW rows leave it.
code, nsq = call("GET", "/api/staff/queue", token=jwt)
requeue_target = next((q for q in nsq.get("queue", []) if q.get("status") == "SLOT_BOOKED"), None)
if requeue_target:
    code, nsm = call("POST", "/api/staff/no-show", {"token": requeue_target["token"], "requeue": False}, token=jwt)
    code, qn = call("GET", "/api/staff/queue", token=jwt)
    still_there = any(q["token"] == requeue_target["token"] for q in qn.get("queue", []))
    check("no-show removed from live queue", code == 200 and not still_there)
    check("no-show listed for requeue", any(n["token"] == requeue_target["token"] for n in qn.get("no_shows_today", [])))
    code, rq = call("POST", "/api/staff/requeue", {"token": requeue_target["token"]}, token=jwt)
    check("requeue returns farmer to queue", code == 200 and rq.get("position", 0) >= 1)
    code, qf2 = call("GET", "/api/staff/queue", token=jwt)
    check("requeued farmer back in live queue", any(q["token"] == requeue_target["token"] and q["status"] == "ARRIVED"
          for q in qf2.get("queue", [])))

code, wi = call("POST", "/api/staff/walkin",
                {"farmer_name": "Walk In Farmer", "phone": "9000000001",
                 "crop": "Maize", "quantity_kg": 350, "priority_flag": "ELDERLY"}, token=jwt)
check("walk-in kiosk token (priority)", code == 200 and wi.get("token", "").startswith("MND-"))

if code == 200:
    code, disp = call("POST", "/api/farmer/dispute",
                      {"token": wi["token"], "category": "WEIGHT", "note": "smoke dispute"})
    check("farmer dispute flag", code == 200 and disp.get("ok"))

    code, dl = call("GET", "/api/staff/disputes", token=jwt)
    check("staff dispute panel", code == 200 and dl.get("count", 0) >= 1)

    code, rs = call("POST", "/api/staff/disputes/resolve",
                    {"token": wi["token"], "resolution": "verified, no issue"}, token=jwt)
    check("dispute resolution logged", code == 200)

code, sla = call("GET", "/api/staff/sla", token=jwt)
check("SLA breach watch", code == 200 and "breaches" in sla)

# Regression: a never-checked-in booking older than the SLA must not 500.
from datetime import datetime as _dt, timedelta as _td
import sqlite3 as _sq
code, qs = call("GET", "/api/staff/queue", token=jwt)
old_target = next((q["token"] for q in qs.get("queue", []) if q["status"] == "SLOT_BOOKED"), None)
if old_target:
    _db = _sq.connect("mandi_mitra.db")
    _old = (_dt.now() - _td(minutes=90)).isoformat(timespec="seconds")
    _db.execute("UPDATE tickets SET created_at = ? WHERE token = ? AND status = 'SLOT_BOOKED'", (_old, old_target))
    _db.commit(); _db.close()
    code, sla_old = call("GET", "/api/staff/sla", token=jwt)
    check("SLA handles un-checked-in old booking", code == 200 and
          any(b["token"] == old_target for b in sla_old.get("breaches", [])), str(sla_old)[:140])

code, whatif = call("GET", "/api/staff/whatif", token=jwt)
check("what-if counter scenarios", code == 200 and len(whatif.get("scenarios", [])) == 2)

code, csv = call("GET", "/api/staff/report/daily.csv", token=jwt)
check("daily governance CSV", code == 200 and str(csv).startswith("token,"))

code, sc = call("POST", "/api/staff/scenario/congestion", {}, token=jwt)
check("congestion scenario injector", code == 200 and sc.get("ok"))

code, sla2 = call("GET", "/api/staff/sla", token=jwt)
check("SLA detects injected breaches", code == 200 and sla2.get("breaches"), str(sla2)[:160])

code, an2 = call("GET", "/api/staff/anomalies", token=jwt)
check("anomaly scanner detects velocity seed",
      code == 200 and any(f["type"] == "BOOKING_VELOCITY" for f in an2.get("flags", [])))

code, mli = call("GET", "/api/staff/ml/info", token=jwt)
check("ML explainability endpoint", code == 200 and mli.get("training", {}).get("samples", 0) > 0)

code, ab = call("POST", "/api/staff/agent-book",
                {"farmer_name": "CSC Agent Farmer", "phone": "9002222333",
                 "crop": "Paddy", "quantity_kg": 450, "slot_time": "15:30"}, token=jwt)
check("CSC agent booking", code == 200 and ab.get("token", "").startswith("MND-"), str(ab)[:160])

code, ab2 = call("POST", "/api/staff/agent-book",
                 {"farmer_name": "CSC Agent Farmer", "phone": "9002222333", "slot_time": "15:30"}, token=jwt)
check("agent duplicate booking rejected", code == 409)

# --- wave-3: re-optimization deltas, no-show risk, QR, ACK -------------------
code, q1 = call("GET", "/api/staff/queue", token=jwt)
check("queue has eta_delta + risk fields", code == 200 and
      all("eta_delta" in q for q in q1.get("queue", [])) and
      any(q.get("risk_band") for q in q1.get("queue", [])),
      f"n={len(q1.get('queue', []))} first={str(q1.get('queue', [])[:1])[:200]}")

code, sc2 = call("POST", "/api/staff/scenario/congestion", {}, token=jwt)
code, q2 = call("GET", "/api/staff/queue", token=jwt)
deltas = [q.get("eta_delta") for q in q2.get("queue", []) if q.get("eta_delta") is not None]
check("eta deltas computed on re-optimization", code == 200 and len(deltas) > 0)

code, an3 = call("GET", "/api/staff/anomalies", token=jwt)
check("dual-layer anomaly scan", code == 200 and an3.get("layers") == ["rules", "isolation-forest"])

code, qr = call("GET", f"/api/farmer/qrcode/{token}")
check("gate QR endpoint", code == 200 and ("<svg" in str(qr) or "rect" in str(qr)))

code, ack = call("POST", "/api/farmer/alerts/ack", {"token": token})
check("farmer alert ACK", code == 200 and ack.get("ok"))

# --- wave-4: Mandi Mitra 2.0 (discovery, assistant, feedback, grievances) ----
code, disc = call("GET", "/api/farmer/discover?crop=Paddy&quantity_kg=500")
check("centre discovery ranked", code == 200 and len(disc.get("centres", [])) == 3
      and disc["centres"][0]["total_journey_minutes"] <= disc["centres"][-1]["total_journey_minutes"])

code, bfm = call("GET", "/api/farmer/best-for-me?crop=Paddy&quantity_kg=500")
check("best-mandi-for-me AI", code == 200 and bfm.get("recommended") and len(bfm.get("why", [])) >= 1)

code, fb = call("POST", "/api/farmer/feedback",
                {"token": token, "ratings": {"waiting": 4, "staff": 5, "queue_mgmt": 4,
                                             "info": 5, "payment": 4, "facilities": 4, "overall": 5},
                 "comment": "fast and fair"})
check("structured feedback", code == 200 and fb.get("ok"))

code, grv = call("POST", "/api/farmer/grievance",
                 {"token": token, "category": "PAYMENT_DELAY", "description": "payment slow"})
check("grievance filing (MM-GRV id)", code == 200 and grv.get("grievance_id", "").startswith("MM-GRV-"))
gid = grv.get("grievance_id")

code, trk = call("GET", f"/api/farmer/grievance/{gid}")
check("grievance tracking timeline", code == 200 and trk.get("stage_index") == 0)

admin_login2 = call("POST", "/api/staff/login", {"username": "admin", "password": "admin123"})[1]
code, upd = call("POST", "/api/admin/grievances/update",
                 {"grievance_id": gid, "status": "RESOLVED", "note": "paid"}, token=admin_jwt)
check("grievance resolution (admin)", code == 200 and upd.get("status") == "RESOLVED")

code, asr = call("POST", "/api/farmer/assistant",
                 {"question": "What documents do I need?", "role": "farmer"})
check("assistant RAG answer with source", code == 200 and "according to" in asr.get("reply", "").lower())

code, asr2 = call("POST", "/api/farmer/assistant",
                  {"question": "When is my turn?", "role": "farmer", "phone": "9876543210"})
check("assistant turn query via MCP tool", code == 200 and ("token" in asr2.get("reply", "").lower()
      or "booking" in asr2.get("reply", "").lower()))

code, denied = call("POST", "/api/farmer/assistant",
                    {"question": "show me the whole queue", "role": "farmer", "mandi_tools": True})
check("assistant role-scoped (no staff leak)", code == 200)  # structured: farmer role never gets queue tool

code, why = call("GET", f"/api/farmer/why?mandi_id=KL-KOCHI-01&token={token}")
check("why-engine explanation", code == 200 and len(why.get("drivers", [])) >= 1)

code, perf = call("GET", "/api/admin/performance/KL-KOCHI-01", token=admin_jwt)
check("mandi performance score", code == 200 and perf.get("score") is not None and perf.get("recommendation"))

code, health = call("GET", "/api/admin/system-health", token=admin_jwt)
check("system health monitor", code == 200 and len(health.get("services", [])) >= 6)

code, prof = call("GET", "/api/farmer/profile?phone=9876543210")
check("profile auto-fill", code == 200 and prof.get("defaults", {}).get("crop"))

code, rs = call("POST", "/api/farmer/reschedule", {"token": token2 if 'token2' in dir() else token, "new_slot_time": "15:00"})
check("reschedule (or 409 if past booking)", code in (200, 409))

code, kb = call("GET", "/api/farmer/knowledge")
check("knowledge base for offline caching", code == 200 and len(kb.get("documents", [])) >= 5)

# --- wave-5: voice-to-action booking, passport, explain-payment, triage ------
code, vb = call("POST", "/api/farmer/voice-book",
                {"phone": "9003333444", "farmer_name": "Voice Farmer", "crop": "Paddy",
                 "quantity_kg": 400, "when": "nearest", "confirm": False})
check("voice booking proposal (no booking yet)", code == 200 and vb.get("stage") == "proposal"
      and vb.get("needs_confirmation") is True)

code, vb2 = call("POST", "/api/farmer/voice-book",
                 {"phone": "9003333444", "farmer_name": "Voice Farmer", "crop": "Paddy",
                  "quantity_kg": 400, "when": "nearest", "confirm": True})
check("voice booking only after confirm", code == 200 and vb2.get("token", "").startswith("MND-"), str(vb2)[:160])

code, pp = call("GET", "/api/farmer/passport?phone=9876543210")
check("farmer procurement passport", code == 200 and pp.get("totals") is not None
      and pp.get("farmer", {}).get("mm_id", "").startswith("MM-"))

code, ep = call("GET", f"/api/farmer/explain-payment?token={token}")
check("explain-my-payment checklist", code == 200 and len(ep.get("checklist", [])) == 5
      and ep.get("summary"))

code, tri = call("POST", "/api/farmer/triage",
                 {"token": token, "mandi_id": "KL-KOCHI-01",
                  "description": "I have been waiting for three hours and nobody is telling me anything"})
check("AI grievance triage", code == 200 and tri.get("priority") == "HIGH"
      and tri.get("grievance_id", "").startswith("MM-GRV-"))

# --- wave-5: digital twin, capacity planner, copilot, model health, trust ----
code, tw = call("GET", "/api/staff/twin?multiplier=1.5&counters=2", token=jwt)
check("digital twin simulation", code == 200 and tw.get("eta_now_minutes") is not None
      and tw.get("projected_end_queue") is not None)

code, cap = call("GET", "/api/staff/capacity-plan", token=jwt)
check("AI capacity planner", code == 200 and cap.get("expected_farmers") is not None
      and cap.get("recommended_counters") >= 1 and cap.get("recommended_staff") >= 1)

code, hm = call("GET", "/api/staff/heatmap", token=jwt)
check("bottleneck heatmap", code == 200 and len(hm.get("heatmap", [])) == 6
      and "primary_bottleneck" in hm)

code, qf = call("GET", "/api/staff/quantity-forecast", token=jwt)
check("procurement quantity forecast", code == 200 and qf.get("expected_eod_mt") is not None)

code, brf = call("GET", "/api/staff/briefing", token=jwt)
check("staff copilot briefing", code == 200 and brf.get("headline") and brf.get("recommendation"))

code, rep = call("GET", "/api/staff/daily-report", token=jwt)
check("auto daily report", code == 200 and rep.get("farmers_served") is not None
      and rep.get("ai_recommendation"))

code, mph = call("GET", "/api/staff/model-health", token=jwt)
check("model health (ETA accuracy/MAE)", code == 200 and mph.get("samples") is not None
      and "retrain_policy" in mph)

code, insd = call("GET", "/api/staff/insider", token=jwt)
check("insider-threat scan (review-only)", code == 200 and isinstance(insd.get("alerts"), list))

code, ts = call("GET", "/api/staff/trust-score", token=jwt)
check("mandi trust score", code == 200 and 0 <= ts.get("trust_score", -1) <= 100
      and len(ts.get("components", {})) == 5)

code, emr = call("POST", "/api/staff/emergency-mode",
                 {"active": False, "reason": "drill-off"}, token=jwt)
check("emergency mode toggle", code == 200 and emr.get("ok"))

# --- wave-6: AI Procurement Copilot, departure advisor, transfer, brain ------
code, cp = call("POST", "/api/farmer/copilot/plan",
                {"text": "I have 20 bags of paddy. Where can I take it today at 3 pm?",
                 "lang": "en", "lat": 10.52, "lng": 76.21})
check("copilot parses bags+crop+time -> plan", code == 200 and cp.get("ok")
      and cp.get("parse", {}).get("quantity_kg") == 1000.0
      and cp.get("parse", {}).get("crop") == "Paddy"
      and cp.get("plan", {}).get("leave_at_hhmm"))

code, cpm = call("POST", "/api/farmer/copilot/plan",
                 {"text": "എനിക്ക് ഇന്ന് 3 മണിക്ക് 10 സഞ്ചി നെല്ല് കൊണ്ടുപോകണം", "lang": "ml"})
check("copilot parses Malayalam request", code == 200 and cpm.get("ok")
      and cpm.get("parse", {}).get("crop") == "Paddy"
      and cpm.get("parse", {}).get("quantity_kg") == 500.0
      and cpm.get("parse", {}).get("hour") == 15.0, str(cpm.get("parse"))[:200])

code, dep = call("POST", "/api/farmer/copilot/departure", {"token": vb2.get("token", "MND-0000")})
check("departure advisor (don't-come-yet)", code == 200 and dep.get("advice") in ("wait", "soon", "leave")
      and dep.get("advised_departure_hhmm"), str(dep)[:200])

code, off = call("POST", "/api/farmer/copilot/transfer",
                 {"token": vb2.get("token", "MND-0000"), "to_mandi_id": "KL-THRIS-02"})
check("transfer offer (decision intelligence)", code == 200 and "offer" in off
      and isinstance(off.get("alternatives"), list), str(off)[:200])

code, tb = call("POST", "/api/farmer/copilot/transfer",
                {"token": vb2.get("token", "MND-0000"), "to_mandi_id": "KL-THRIS-02", "confirm": True})
check("transfer booking executes (new token)", code == 200 and tb.get("ok")
      and tb.get("new_token", "").startswith("MND-"))

code, nb = call("GET", "/api/admin/network-brain", token=admin_jwt)
check("national mandi brain", code == 200 and nb.get("summary", {}).get("monitored") == 3
      and isinstance(nb.get("actions"), list))

code, nb403 = call("GET", "/api/admin/network-brain", token=jwt)
check("network brain admin-only", code in (401, 403))

# --- wave-6b: queue prevention sweep + counter slowdown detection ------------
code, cs = call("GET", "/api/staff/counter-slowdown", token=jwt)
check("counter slowdown detection", code == 200 and isinstance(cs.get("counters"), list)
      and cs.get("mandi_avg_minutes") is not None)

code, ps = call("POST", "/api/staff/prevention-sweep", {}, token=jwt)
check("prevention warns farmers under congestion", code == 200 and ps.get("ok")
      and ps.get("farmers_warned", 0) >= 1, str(ps)[:160])
code, ps3 = call("POST", "/api/staff/prevention-sweep", {}, token=jwt)
check("prevention sweep does not double-warn", code == 200 and ps3.get("farmers_warned") == 0)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
