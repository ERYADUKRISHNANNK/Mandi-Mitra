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
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


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
check("SMS booking channel", code == 200 and "Booked" in sms.get("reply", ""))

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

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
