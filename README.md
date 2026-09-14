# 🌾 Mandi Mitra 2.0 — AI-Powered National Smart Procurement Network

**Know the Mandi. Know your Turn. Know your Payment.**

> **Farmers don't need to understand the technology. Mandi Mitra understands the farmer.**
> The farmer speaks naturally in their own language; the AI copilot decides the best centre, the best time, and when to leave home — all the intelligence lives underneath, none of the jargon reaches the farmer.

A working full-stack prototype for Smart India Hackathon (SIH26032), evolved from a queue-visibility system into a **national intelligent procurement platform**: farmers discover and compare nearby centres, get AI "Best Mandi For Me" recommendations, book through five access modes, receive predictive turn/departure alerts, and track procurement + payment end-to-end — while staff, district and national administrators get role-scoped operational intelligence. Offline-first, multilingual (en/ml/hi/ta), and grounded by a RAG knowledge layer with MCP-style controlled tools.

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
| **Demo controls everywhere** | ✅ working | Farmer: sample copilot prompts + 1-tap demo booking · Staff: 🎬 1-click demo (scenario + autopilot) · Admin: 🎬 District demo (congestion + movement in every centre + prevention sweep) |
| **Smart diversion (load balancing)** | ✅ working | Congested mandi? Suggests a nearby centre with real distances, drive time & fuel cost — farmer decides |
| GPS self check-in | ✅ working | Farmer checks in from the PWA geofence (2.5 km) — no desk queue |
| Priority inclusion | ✅ working | Elderly / differently-abled / small-holder precedence at booking and walk-in |
| Walk-in kiosk tokens | ✅ working | Staff issue instant tokens to unbooked farmers — they join the live queue |
| No-show handling + requeue | ✅ working | No-shows leave the live queue (no ghost ETAs); staff can requeue them later — behind arrivals, ahead of walk-ins, with SMS confirmation |
| Public hall board | ✅ working | "Now Serving / Next Up" display for centre halls, auto-refreshing |
| Farmer disputes (evidence) | ✅ working | Immutable timestamped flags on weight/quality/payment with staff resolution logging |
| SLA breach watch | ✅ working | Banner alert when any farmer waits beyond the service threshold |
| What-if intelligence | ✅ working | Quantified impact of opening/closing a counter before deciding |
| Governance CSV report | ✅ working | One-click daily per-farmer report incl. minutes-in-mandi |
| **Congestion scenario injector** | ✅ working | One click fills the mandi with realistic load — SLA breaches, stuck stages, delayed payments, velocity anomalies all light up live |
| **Voice output (TTS)** | ✅ working | Farmer token screen speaks status aloud via Web Speech; IVR call simulation plays real audio in the room |
| **Live SMS/IVR channel feed** | ✅ working | Staff see every message the system sends, in all 4 languages, in real time |
| **ML explainability** | ✅ working | `/api/staff/ml/info` exposes algorithm, features, R², sample count and the fallback story — no black-box claims |
| **CSC agent booking** | ✅ working | VLE agent books on behalf of farmers with no phone at all — the government adoption path |
| Impact metrics | ✅ working | Farmer-hours saved today, avg time-at-centre vs 4h baseline, on the admin dashboard |
| **National centre discovery** | ✅ working | Nearby centres ranked by TOTAL JOURNEY time (travel + queue + processing) with live status, source-stamped rate, experience rating |
| **"Best Mandi For Me" AI** | ✅ working | One recommendation with reasons (journey, queue, rating) + alternatives |
| **Live centre status** | ✅ working | Staff-settable OPEN/PAUSED/WEATHER… states surfaced in discovery & booking |
| **Rate transparency** | ✅ working | ₹/quintal + estimated value — always with source + updated timestamp (no fake-official numbers) |
| **Structured feedback + experience score** | ✅ working | 6-dimension ratings feed the mandi's public experience score |
| **Grievance lifecycle** | ✅ working | MM-GRV tracking IDs, 5-stage timeline, admin resolution |
| **RAG assistant (grounded)** | ✅ working | Official-doc answers WITH source + date; refuses to invent; 4 languages; voice output |
| **MCP-style tool layer** | ✅ working | Assistant reaches data only through role-authorized tools (LLM → tool → authz → data) |
| **"Why?" explainable engine** | ✅ working | Real drivers behind your wait: offline counters, arrival spikes, stuck stages |
| **Mandi performance score** | ✅ working | Composite score + top-bottleneck recommendation for administrators |
| **System health monitor** | ✅ working | National service board + online/offline mandi counts |
| **Reschedule / cancel / auto-fill** | ✅ working | Full booking lifecycle; profile auto-fill from verified history |
| **🔮 Digital Twin simulator** | ✅ working | Simulate the rest of the day under any scenario (counters, arrival surge) in milliseconds — predicted end-of-day queue, peak queue, ETA impact — before deciding |
| **AI Capacity Planner** | ✅ working | Tomorrow's expected farmers/volume/peak window → recommended counters, staff and slot capacity |
| **Bottleneck heatmap** | ✅ working | Where waiting farmers are held, stage by stage, with the primary bottleneck named |
| **Quantity forecast** | ✅ working | Received MT, expected remaining, projected end-of-day procurement volume |
| **Staff Copilot briefing** | ✅ working | Morning intelligence: expected load, peak window, recommended counters, payments needing attention, SLA breaches now |
| **Auto daily report** | ✅ working | One-click generated report: served/completed/no-shows/avg wait/peak hour/payments/bottleneck + AI recommendation |
| **AI model monitoring** | ✅ working | ETA accuracy %, MAE, sample count, declared retrain policy — self-learning story backed by numbers |
| **Insider-threat review** | ✅ working | Behavioural flags on staff accounts (manual interventions, unusual hours) — AI-assisted, human decides |
| **Mandi Trust Score** | ✅ working | Transparent weighted composite (queue efficiency, payment reliability, information accuracy, grievance resolution, farmer rating) |
| **Farmer procurement passport** | ✅ working | Per-farmer history: visits, completions, earnings, avg time — per crop, private to the farmer |
| **Explain My Payment** | ✅ working | 5-step checklist from real records (approval → bank confirmation) — never invented, flags delay review |
| **Voice-to-action booking** | ✅ working | "Book tomorrow at the nearest mandi" → AI proposes, **explicit confirmation required** before anything is booked |
| **AI grievance triage** | ✅ working | Classifies category + priority from text (HIGH routes to district officer) and files an MM-GRV case |
| **Emergency Procurement Mode** | ✅ working | One click freezes bookings, marks the centre CLOSED, notifies affected farmers, points to alternatives |
| **🧠 AI Procurement Copilot** | ✅ working | Farmer speaks naturally ("ഇന്ന് 10 സഞ്ചി നെല്ല് 3 മണിക്ക്") → ONE plan: best centre, leave-at time, expected wait, est. value, documents to carry, savings vs the worst option. Multilingual parser (en/ml/hi/ta), bags→kg, mic input |
| **"Don't come yet" departure advisor** | ✅ working | Live-recomputed advice: wait / get-ready / leave-now with the exact start time — attacks blind waiting directly |
| **Intelligent rebooking (transfer)** | ✅ working | When load shifts, the system offers a better centre with quantified savings; farmer confirms; transfer re-slots with priority |
| **Simple Mode** | ✅ working | Farmer-simple big-button UI (MY TURN / START AT / PAYMENT / LISTEN) — zero jargon, all AI underneath |
| **🇮🇳 National Mandi Brain** | ✅ working | Admin intelligence: tomorrow's overloaded centres, underutilized centres, payment hotspots + recommended action list |
| **🛡 Queue PREVENTION sweep** | ✅ working | Detects congested centres and warns still-at-home farmers BEFORE they travel (multilingual stay-home SMS + alternative centre) — preventing the queue, not monitoring it; idempotent |
| **⚠ Counter slowdown detection** | ✅ working | Flags counters >30% slower than the centre average from the audit trail with staffing recommendation — the mandi side of the intelligence |

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

**Verify everything:** `backend/.venv/Scripts/python backend/scripts/smoke_test.py` → **90 checks**, covering booking→payment→receipt, SMS/missed-call/IVR, autopilot, command centre, auth guards, self check-in, walk-in, disputes, SLA, what-if, CSV, diversion, hall board, ETA deltas, no-show risk, dual-layer anomalies, QR, escalation, discovery, best-mandi AI, feedback, grievances, RAG assistant, MCP authorization, why-engine, performance score, system health, auto-fill, reschedule, voice-to-action booking, passport, explain-payment, triage, digital twin, capacity plan, heatmap, quantity forecast, copilot briefing, daily report, model health, insider scan, trust score, emergency mode, multilingual copilot parsing (en+ml), departure advisor, transfer offer/booking, the national brain, the prevention sweep, counter-slowdown detection and the no-show → requeue cycle.

## 🎬 5-minute demo script

1. **Farmer books (1 min)** — open the PWA in Malayalam and tap a **💬 sample prompt** ("I have 20 bags of paddy for today 3 pm") → the copilot answers with one plan. Or tap **🎬 1-tap demo booking** for an instant live token. The **Leave-home banner** and departure advisor fire on their own.
2. **Feature-phone parity (30 sec)** — `POST /api/sms {"phone":"…","message":"BOOK KL-KOCHI-01 WHEAT 700"}` and `POST /api/missed-call` → instant Malayalam IVR status. No app needed.
3. **Staff dashboard (1.5 min)** — login staff1 → **🎬 1-click demo** (scenario + autopilot): the queue moves stage-by-stage in real time, ETAs shrink live, SLA banner turns red. Point at the AI recommendations, twin and heatmap as they light up.
4. **Transparency (1 min)** — complete a farmer's journey → receipt with **hash + chain verified ✅**; show admin **audit trail** per token.
5. **Command centre (1 min)** — login admin → **🎬 District demo**: congestion + live movement in every centre + prevention sweep in one click; the map turns red where it matters. Bonus beats: show the **hall board** on a second screen, raise a farmer **dispute** and resolve it from staff, and open the **what-if** card ("opening C2 cuts wait from 41m to 21m"). Close: **"Know your turn. Reach when it matters."**

**Wave-5 demo beats (pick 1–2):** run the **Digital Twin** ("×2 arrivals, 2 counters → projected peak queue 14") before opening a counter; fire the **⚡ Congestion scenario** and watch the copilot briefing, SLA banner and heatmap turn red together; use **voice booking** ("book tomorrow at the nearest mandi" → AI proposal → explicit confirm); open **Daily report** for the auto-generated bottleneck recommendation.

**Wave-6 demo beat (the opener):** on the farmer screen type or *speak*: `I have 20 bags of paddy for today 3 pm` → the **AI Procurement Copilot** replies with one plan (centre, leave-at time, wait, ₹ value, documents, savings) → one tap books it. Then show **Simple Mode** (big buttons, zero jargon) and finish on the admin **National Mandi Brain**. Closing line: **"Farmers don't need to understand the technology. Mandi Mitra understands the farmer."**

## 🧠 The four AI modules (all explainable)

1. **Wait-time ETA** — ridge regression on hourly history; R² + sample count exposed; analytic fallback declared; confidence % on every ETA
2. **Congestion forecast** — history + live arrival-rate blending per hour
3. **Anomaly detection** — rules + IsolationForest, review-only flags
4. **No-show risk** — transparent weighted signals with reasons on every chip

Plus: **Best-Mandi-For-Me** ranking (total journey time + availability + reputation), the **"Why?" engine** that explains waits from real operational drivers, and **model monitoring** (ETA accuracy %, MAE, declared retrain policy) — the self-learning story backed by numbers.

## 🔮 Intelligence layers (the demo story)

Mandi Mitra isn't a feature dump — it's four coherent intelligence layers over one platform:

1. **Farmer Intelligence** — *where should I go and when should I leave?* → discovery + best-mandi AI + leave-home alerts + voice booking
2. **Queue Intelligence** — *who is next and what will the wait be?* → dynamic queue engine + ETA deltas + no-show risk + smart slots
3. **Mandi Intelligence** — *where is the bottleneck and what should staff do?* → digital twin + capacity planner + heatmap + copilot briefing + daily report
4. **Government Intelligence** — *where are congestion, delays and grievances occurring?* → command centre + trust scores + insider review + system health + triage

## 📚 Knowledge layer (RAG + MCP)

- `knowledge_docs` seeded with sourced prototype documents (guidelines, MSP, payment circulars, grievance policy)
- Retrieval answers ALWAYS cite `title · source · updated` and refuse to invent when confidence is low
- The assistant cannot touch the DB directly — it calls `TOOLS` (`get_farmer_status`, `find_nearby_centres`, `get_official_guidelines`, …), each declaring allowed roles

## 🏆 Why this wins (competitive analysis)

Most teams will demo a booking app with a token number. Mandi Mitra demos an **operating system for procurement centres**:

| Judge question | Typical team | Mandi Mitra |
|---|---|---|
| "Farmer has no smartphone?" | "…we assume a smartphone" | SMS grammar + missed-call IVR + voice TTS + CSC agent booking — four fallback layers |
| "Show me real-time" | Page refresh | WebSocket fan-out, live positions, ETA deltas on every event |
| "Show me the AI" | "we use scikit-learn" (hand-wave) | Ridge model with exposed R²/samples + declared analytic fallback + confidence on every ETA |
| "What happens when it's crowded?" | Blank stare | Congestion forecast, what-if counter scenarios, diversion advice, SLA watch, IVR broadcast |
| "Prove the record wasn't tampered" | "blockchain!" (no working code) | Working SHA-256 hash-chain receipts, one-click chain verification |
| "Will fraud happen?" | Not considered | Booking-velocity, no-show, stuck-stage, irregularity and outlier flags for review |
| "Does it work offline?" | No | Service-worker cached status + offline banner |
| "How does govt deploy it?" | "…an app" | Multi-tenant by mandi_id, district command centre, CSC adoption path, CSV governance reports |
| "Is it tested?" | Manual clicking | 76-check automated end-to-end suite, all passing |
| "Can it plan ahead, not just react?" | Dashboard-only | Digital-twin simulation, AI capacity planner, quantity forecast, congestion waves |
| "What if staff misbehave?" | Not considered | Behavioural insider flags (review-only) + immutable audit trail + emergency mode |

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
