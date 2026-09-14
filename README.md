# 🌾 Mandi Mitra — Smart Procurement Queue & Visibility System

**Know your turn. Reach when it matters.**

A working full-stack prototype built for Smart India Hackathon (SIH26032): farmers no longer wait blindly at MSP procurement centres. Mandi Mitra converts a static token queue into an intelligent, predictive and transparent procurement system — farmers know *when* to arrive, staff know *where* the bottleneck is, and officials get *visibility* across every centre.

---

## ✨ What's inside

| Module | Status | Highlights |
|---|---|---|
| Multi-channel booking | ✅ working | PWA · simulated SMS (`BOOK MANDI CROP QTY`) · missed-call IVR callback · 4 languages |
| AI smart slots | ✅ working | Recommended slot + expected wait + confidence % |
| Dynamic queue engine | ✅ working | Live positions recalculated on every event; serving/waiting/upcoming groups |
| Wait-time prediction | ✅ working | Ridge regression on 30-day synthetic history, analytic fallback, confidence score |
| **Leave-Home alert** | ✅ working | Auto SMS + IVR call when ETA ≤ 45 min; turn-approaching alert at position ≤ 2 |
| Workflow tracking | ✅ working | Slot Booked → Arrived → Weighing → Quality → Payment → Completed, timestamped audit trail |
| Payment intelligence | ✅ working | MSP-based amount, delay detection, status in farmer view |
| Tamper-evident receipts | ✅ working | Per-mandi SHA-256 hash-chain of procurement records; one-click chain verification |
| Trust score | ✅ working | Gamified farmer reliability score shown with status |
| Anomaly detection | ✅ working | Booking velocity, repeat no-shows, stuck stages, queue irregularities, quantity outliers |
| Staff intelligence | ✅ working | Counter utilisation + AI staffing recommendations, IVR broadcast |
| Congestion forecast | ✅ working | Hourly Low/Moderate/High prediction blended from history + live arrivals |
| District command centre | ✅ working | Leaflet map, congestion status, receipt-chain health, district totals |
| Offline-first PWA | ✅ working | Service worker caches last status; offline banner |
| Demo autopilot | ✅ working | One click simulates arrivals & stage progression for judging |
| **Smart diversion (load balancing)** | ✅ working | Congested mandi? Suggests a nearby centre with real distances, drive time & fuel cost — farmer decides |
| GPS self check-in | ✅ working | Farmer checks in from the PWA geofence (2.5 km) — no desk queue |
| Priority inclusion | ✅ working | Elderly / differently-abled / small-holder precedence at booking and walk-in |
| Walk-in kiosk tokens | ✅ working | Staff issue instant tokens to unbooked farmers — they join the live queue |
| Public hall board | ✅ working | "Now Serving / Next Up" display for centre halls, auto-refreshing |
| Farmer disputes (evidence) | ✅ working | Immutable timestamped flags on weight/quality/payment with staff resolution logging |
| SLA breach watch | ✅ working | Banner alert when any farmer waits beyond the service threshold |
| What-if intelligence | ✅ working | Quantified impact of opening/closing a counter before deciding |
| Governance CSV report | ✅ working | One-click daily per-farmer report incl. minutes-in-mandi |

## 🚀 Run it (2 terminals, ~1 minute)

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/Mac
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

On first start it seeds 3 mandis, 30 days of history, staff users and a live demo queue.

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** · API docs at **http://127.0.0.1:8000/docs**

Or double-click **`start_all.bat`** (Windows).

**Logins:** staff `staff1 / staff123` · district admin `admin / admin123`

**Verify everything:** `backend/.venv/Scripts/python backend/scripts/smoke_test.py` → 35 checks, covering booking→payment→receipt, SMS/missed-call/IVR, autopilot, command centre, auth guards, self check-in, walk-in, disputes, SLA, what-if, CSV, diversion and the hall board.

## 🎬 5-minute demo script

1. **Farmer books (1 min)** — open the PWA in Malayalam, pick Kochi, 500 kg paddy → AI recommends "12:30 · wait ~4m · 92% confidence". Book. Token + position + ETA appear instantly; the **Leave-home banner** fires on its own as ETA crosses the threshold. Show the SMS log ("💬 SMS / IVR alerts").
2. **Feature-phone parity (30 sec)** — `POST /api/sms {"phone":"…","message":"BOOK KL-KOCHI-01 WHEAT 700"}` and `POST /api/missed-call` → instant Malayalam IVR status. No app needed.
3. **Staff dashboard (1.5 min)** — login staff1. Point at **AI recommendation**: "C2 idle while N farmers wait — allocate staff now". Run **autopilot**: watch the queue move stage-by-stage in real time, ETAs shrinking, timeline filling.
4. **Transparency (1 min)** — complete a farmer's journey → receipt with **hash + chain verified ✅**; show admin **audit trail** per token.
5. **Command centre (1 min)** — login admin: district map, congestion status, totals, receipt-chain health. Bonus beats: show the **hall board** on a second screen, raise a farmer **dispute** and resolve it from staff, and open the **what-if** card ("opening C2 cuts wait from 41m to 21m"). Close: **"Know your turn. Reach when it matters."**

## 🏗 Architecture

```
Farmer PWA (React) ─┐
SMS gateway (sim)  ─┼─▶ FastAPI ─▶ Queue Engine ─▶ WebSocket fan-out (live queue)
IVR / missed call ─┘        │           │
                            │      ┌────┴─────┬─────────────┐
                            ▼      ▼          ▼             ▼
                     PostgreSQL*  Redis*    ML models    Audit + hash-chain
                    (SQLite now) (in-mem)  (wait/ETA,     receipts
                     slot=swap)  (swap in) congestion,
                                            slots, anomaly)
```

- **Queue engine** (`queue_engine.py`) — recomputes the full mandi queue on every event, drives alerts (leave-home, turn-soon), payment-delay detection.
- **AI layer** — `predictor.py` (ridge regression + analytic fallback + confidence), `congestion.py` (hourly forecast), `slots.py` (recommendation), `anomaly.py` (review-flagging, never auto-accusation).
- **Transparency** — `audit.py` (every action, timestamped, per-token) + `receipts.py` (tamper-evident hash chain).
- **Simulated boundaries** — SMS/IVR gateway, payment, OTP: clearly labelled in code and UI; production swaps `notify.send_sms/send_voice` and the payment step for real gateways without touching business logic.

## 🗺 Prototype → deployment path

| Prototype | Production |
|---|---|
| SQLite + in-memory snapshot | PostgreSQL + Redis (config-level swap) |
| Simulated SMS/IVR | CDAC/MSG91/Twilio gateway, IVR provider |
| Simulated OTP (inline) | Real OTP over SMS |
| Simulated payment completion | PFMS/NFS integration (deployment-dependent) |
| 3 seeded mandis | Multi-tenant by mandi_id, district → state → national |

## 🔐 Security notes

JWT (HS256) with role-based access (STAFF/ADMIN), OTP login simulation, duplicate-booking guard, per-action audit trail, anonymised receipt payloads (phone stored as last-4 only). CORS is open in prototype only. No Aadhaar or government-system integration is claimed — those are deployment-dependent.

## 📁 Layout

```
backend/
  app/
    main.py           FastAPI app, WS, SMS/missed-call channels, impact metrics
    routes_farmer.py  register/OTP/slots/book/status/timeline/receipt/IVR
    routes_staff.py   dashboard/workflow/anomalies/bottleneck/broadcast/autopilot
    queue_engine.py   live queue, positions, ETAs, alerts
    predictor.py congestion.py slots.py anomaly.py receipts.py pricing.py
    i18n.py           en/ml/hi/ta message templates
    db.py seed.py security.py audit.py events.py config.py
  scripts/smoke_test.py   25-check end-to-end suite
frontend/
  src/App.jsx          Farmer + Staff + Admin views
  public/sw.js         offline-first service worker
```
