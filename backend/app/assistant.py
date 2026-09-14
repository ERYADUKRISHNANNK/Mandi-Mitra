"""AI knowledge layer: RAG over the mandi knowledge base + MCP-style tool
registry + the farmer/staff assistant endpoint.

Design principles (deliberate):
  - The assistant NEVER reads the database directly. It goes through the MCP
    tool registry (`TOOLS`), each entry declaring which roles may call it.
    LLM -> tool -> authorization -> backend -> data.
  - RAG answers always cite source + updated date; when retrieval confidence
    is low it says so instead of inventing policy.
  - Dynamic facts (rates, statuses) come from tools, not from training data.
  - Multilingual: knowledge base stores per-language content where relevant.
"""

import re

from .db import query, query_one

# --------------------------------------------------------------------------
# Knowledge base (seeded by seed.py; document store with sources)
# --------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9\u0900-\u097f\u0b80-\u0bff\u0d00-\u0d7f]+", text.lower())


def rag_search(question: str, k: int = 2) -> list[dict]:
    """TF-IDF-ish retrieval over knowledge_docs with a transparent score."""
    docs = query("SELECT * FROM knowledge_docs")
    if not docs:
        return []
    q_terms = set(_tokenize(question))
    if not q_terms:
        return []
    scored = []
    for d in docs:
        d_terms = _tokenize(d["title"] + " " + d["content"])
        if not d_terms:
            continue
        overlap = q_terms & set(d_terms)
        if not overlap:
            continue
        score = len(overlap) / math_sqrt(len(d_terms))
        scored.append({"score": score, "doc": d})
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [{"title": s["doc"]["title"], "source": s["doc"]["source"], "updated": s["doc"]["updated"],
             "content": s["doc"]["content"], "score": round(s["score"], 3)}
            for s in scored[:k] if s["score"] > 0.01]


def math_sqrt(x: float) -> float:
    return x ** 0.5


# --------------------------------------------------------------------------
# MCP-style tool registry — the ONLY way the assistant touches live data.
# Each tool declares allowed roles; calls are audited.
# --------------------------------------------------------------------------

TOOLS: dict[str, dict] = {}


def tool(name: str, roles: set[str], description: str):
    def register(fn):
        TOOLS[name] = {"fn": fn, "roles": roles, "description": description}
        return fn
    return register


@tool("get_farmer_status", roles={"farmer", "staff", "admin"},
      description="Live token status, queue position and ETA for a farmer token/phone")
def t_farmer_status(args, user):
    from .routes_farmer import _find_ticket
    from .queue_engine import get_snapshot, recompute_mandi
    t = _find_ticket(args.get("token"), args.get("phone"))
    if not t:
        return {"error": "No booking found for that token/phone"}
    snap = recompute_mandi(t["mandi_id"])
    mine = next((q for q in snap["queue"] if q["ticket_id"] == t["id"]), None)
    return {"token": t["token"], "status": t["status"],
            "position": mine["position"] if mine else 0,
            "eta_minutes": mine["eta_minutes"] if mine else None,
            "payment_status": t["payment_status"], "amount": t["amount"]}


@tool("get_queue_status", roles={"staff", "admin"},
      description="Live queue summary for a mandi")
def t_queue_status(args, user):
    from .queue_engine import get_snapshot
    snap = get_snapshot(args.get("mandi_id") or user.get("mandi_id") or "KL-KOCHI-01")
    waiting = sum(1 for q in snap["queue"] if q["queue_group"] != "SERVING")
    serving = [q["token"] for q in snap["queue"] if q["queue_group"] == "SERVING"]
    return {"mandi_id": snap["mandi_id"], "waiting": waiting, "serving": serving,
            "avg_wait_minutes": snap["avg_process_minutes"], "processed_today": snap["processed_today"]}


@tool("find_nearby_centres", roles={"farmer", "staff", "admin"},
      description="Rank nearby procurement centres by total journey time")
def t_nearby(args, user):
    from .discovery import discover
    centres = discover(args.get("lat"), args.get("lng"), args.get("crop"), args.get("quantity_kg", 0))
    return {"centres": [{k: c[k] for k in ("mandi_id", "name", "status", "distance_km",
                                           "queue_length", "total_journey_minutes")} for c in centres[:5]]}


@tool("get_mandi_details", roles={"farmer", "staff", "admin"},
      description="Status, rate, rating and load of one centre")
def t_mandi_details(args, user):
    from .discovery import discover, _status_of
    mid = args.get("mandi_id")
    c = next((c for c in discover(crop=args.get("crop")) if c["mandi_id"] == mid), None)
    if not c:
        return {"error": "Unknown centre"}
    return c


@tool("get_procurement_status", roles={"farmer", "staff", "admin"},
      description="Stage-wise procurement + payment status for a token")
def t_procurement(args, user):
    t = query_one("SELECT * FROM tickets WHERE token = ?", (args.get("token"),))
    if not t:
        return {"error": "Unknown token"}
    from .routes_farmer import timeline_events
    return {"token": t["token"], "status": t["status"], "amount": t["amount"],
            "payment_status": t["payment_status"], "timeline": timeline_events(t["id"])[-4:]}


@tool("get_official_guidelines", roles={"farmer", "staff", "admin"},
      description="Search the RAG knowledge base of official documents")
def t_guidelines(args, user):
    hits = rag_search(args.get("question", ""))
    return {"results": hits}


@tool("submit_grievance", roles={"farmer"},
      description="File a grievance and return its tracking ID")
def t_grievance(args, user):
    from .feedback import file_grievance
    return file_grievance(args.get("token"), args.get("phone"), args.get("mandi_id", "KL-KOCHI-01"),
                          args.get("category", "OTHER"), args.get("description", ""))


def call_tool(name: str, args: dict, user: dict) -> dict:
    t = TOOLS.get(name)
    if not t:
        return {"error": f"Unknown tool {name}"}
    if user.get("role", "farmer") not in t["roles"]:
        return {"error": f"Role '{user.get('role')}' not authorized for tool '{name}'"}
    return t["fn"](args, user)


# --------------------------------------------------------------------------
# The assistant: intent routing -> tools + RAG -> grounded answer
# --------------------------------------------------------------------------

INTENTS = [
    ("turn", [r"my turn", r"when.*turn", r"queue position", r"how long", r"eta", r"wait"]),
    ("payment", [r"payment", r"paid", r"amount", r"money"]),
    ("documents", [r"document", r"paper", r"carry", r"proof"]),
    ("nearby", [r"nearby", r"nearest", r"which mandi", r"other cent", r"less crowd"]),
    ("procedure", [r"process", r"how.*procure", r"steps", r"quality check", r"weighing"]),
    ("grievance", [r"complaint", r"grievance", r"issue.*report", r"problem"]),
]


def assistant_reply(question: str, user: dict) -> dict:
    q = question.lower()
    tool_calls = []

    def use(name, args):
        tool_calls.append({"tool": name, "args": args})
        return call_tool(name, args, user)

    intent = next((i for i, pats in INTENTS if any(re.search(p, q) for p in pats)), None)

    if intent == "turn" and (user.get("token") or user.get("phone")):
        r = use("get_farmer_status", {"token": user.get("token"), "phone": user.get("phone")})
        if "error" not in r:
            pos = r["position"]
            eta = r["eta_minutes"]
            return {"reply": f"Your token {r['token']} is {r['status'].replace('_', ' ').lower()}. "
                             f"Position {pos}, expected wait about {eta} minutes.",
                    "tool_calls": tool_calls}
        return {"reply": "I couldn't find an active booking for you. Book via app, SMS (BOOK <mandi> <crop> <qty>) or a missed call.",
                "tool_calls": tool_calls}

    if intent == "payment" and (user.get("token") or user.get("phone")):
        r = use("get_farmer_status", {"token": user.get("token"), "phone": user.get("phone")})
        if "error" not in r:
            if r["payment_status"] == "COMPLETED":
                return {"reply": f"Your payment of ₹{int(r['amount'] or 0)} is complete. The digital receipt with tamper-evident hash is in your app.",
                        "tool_calls": tool_calls}
            if r["payment_status"] == "PROCESSING":
                return {"reply": f"Procurement is approved (₹{int(r['amount'] or 0)}) and payment is in the banking pipeline. You'll get an SMS the moment it lands.",
                        "tool_calls": tool_calls}
            if r["payment_status"] == "DELAYED":
                return {"reply": f"Your payment of ₹{int(r['amount'] or 0)} has crossed the normal processing window and is flagged for priority review by the mandi officer.",
                        "tool_calls": tool_calls}
        return {"reply": "Payment tracking needs your token or registered phone.", "tool_calls": tool_calls}

    if intent == "documents":
        hits = rag_search("documents required farmer procurement")
        if hits:
            h = hits[0]
            return {"reply": f"According to '{h['title']}' ({h['source']}, updated {h['updated']}): {h['content'][:280]}",
                    "sources": hits, "tool_calls": tool_calls}

    if intent == "nearby":
        r = use("find_nearby_centres", {"lat": user.get("lat"), "lng": user.get("lng"),
                                        "crop": user.get("crop")})
        names = ", ".join(f"{c['name']} ({c['queue_length']} in queue, ~{c['total_journey_minutes']}m total)"
                          for c in r["centres"][:3])
        return {"reply": f"Centres ranked by total journey time: {names}.",
                "tool_calls": tool_calls}

    if intent == "grievance":
        return {"reply": "You can raise a grievance from the app (Raise a concern) or by SMS. "
                         "You'll get an MM-GRV tracking ID and the status timeline is visible to you end-to-end.",
                "tool_calls": tool_calls}

    # Default: RAG over official knowledge base.
    hits = rag_search(question)
    if hits:
        h = hits[0]
        return {"reply": f"From the official knowledge base ('{h['title']}', {h['source']}, updated {h['updated']}): {h['content'][:280]}",
                "sources": hits, "tool_calls": tool_calls}

    return {"reply": "I can help with your turn, payment status, required documents, nearby centres and grievances. "
                     "For anything else, contact the mandi officer.",
            "tool_calls": tool_calls}
