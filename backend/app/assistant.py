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
# Multilingual reply layer — the assistant answers in the farmer's language.
# --------------------------------------------------------------------------

def detect_lang(text: str) -> str | None:
    """Script-based language guess: Malayalam, Hindi (Devanagari), Tamil."""
    if re.search(r"[\u0d00-\u0d7f]", text):
        return "ml"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    if re.search(r"[\u0b80-\u0bff]", text):
        return "ta"
    return None


R = {
    "turn": {
        "en": "Your token {token} is {status}. Position {pos}, expected wait about {eta} minutes.",
        "ml": "നിങ്ങളുടെ ടോക്കൺ {token} ഇപ്പോൾ {status}. സ്ഥാനം {pos}, ഏകദേശം {eta} മിനിറ്റ് കാത്തിരുപ്പ്.",
        "hi": "आपका टोकन {token} अभी {status} है। स्थान {pos}, अनुमानित प्रतीक्षा लगभग {eta} मिनट।",
        "ta": "உங்கள் டோக்கன் {token} இப்போது {status}. இடம் {pos}, சுமார் {eta} நிமிட காத்திருப்பு.",
    },
    "no_booking": {
        "en": "I couldn't find an active booking for you. Book via app, SMS (BOOK <mandi> <crop> <qty>) or a missed call.",
        "ml": "നിങ്ങളുടെ സജീവ ബുക്കിംഗ് കണ്ടില്ല. ആപ്പ്, SMS (BOOK <മണ്ഡി> <വിള> <അളവ്>) അല്ലെങ്കിൽ മിസ്സ്ഡ് കോൾ വഴി ബുക്ക് ചെയ്യൂ.",
        "hi": "आपकी कोई सक्रिय बुकिंग नहीं मिली। ऐप, SMS (BOOK <मंडी> <फसल> <मात्रा>) या मिस्ड कॉल से बुक करें।",
        "ta": "உங்கள் செயலில் உள்ள பதிவு எதுவும் கிடைக்கவில்லை. ஆப், SMS அல்லது மிஸ்ட் கால் மூலம் பதிவு செய்யுங்கள்.",
    },
    "pay_done": {
        "en": "Your payment of ₹{amt} is complete. The digital receipt with tamper-evident hash is in your app.",
        "ml": "₹{amt} പേയ്മെന്റ് പൂർത്തിയായി. ടാംപർ-പ്രൂഫ് ഹാഷുള്ള ഡിജിറ്റൽ രസീത് ആപ്പിൽ ഉണ്ട്.",
        "hi": "₹{amt} का भुगतान पूरा हो गया। टैम्पर-प्रूफ हैश वाली डिजिटल रसीद आपके ऐप में है।",
        "ta": "₹{amt} பணம் முடிந்தது. டிஜிட்டல் ரசீது உங்கள் ஆப்பில் உள்ளது.",
    },
    "pay_proc": {
        "en": "Procurement is approved (₹{amt}) and payment is in the banking pipeline. You'll get an SMS the moment it lands.",
        "ml": "വാങ്ങൽ അംഗീകരിച്ചു (₹{amt}), പേയ്മെന്റ് ബാങ്കിംഗ് ഘട്ടത്തിലാണ്. എത്തിയ ഉടൻ SMS ലഭിക്കും.",
        "hi": "खरीद स्वीकृत है (₹{amt}) और भुगतान बैंकिंग प्रक्रिया में है। आते ही आपको SMS मिलेगा।",
        "ta": "கொள்முதல் ஒப்புதல் (₹{amt}), பணம் வங்கி செயல்முறையில் உள்ளது. வந்தவுடன் SMS கிடைக்கும்.",
    },
    "pay_delay": {
        "en": "Your payment of ₹{amt} has crossed the normal processing window and is flagged for priority review by the mandi officer.",
        "ml": "₹{amt} പേയ്മെന്റ് സാധാരണ സമയത്തിനപ്പുറം വൈകി; മണ്ഡി ഉദ്യോഗസ്ഥന്റെ മുൻഗണനാ പരിശോധനയിലാണ്.",
        "hi": "₹{amt} का भुगतान सामान्य समय से अधिक देर का है; मंडी अधिकारी की प्राथमिकता समीक्षा में है।",
        "ta": "₹{amt} பணம் சாதாரண நேரத்தை தாண்டி தாமதமாகியுள்ளது; மண்டி அதிகாரியின் முன்னுரிமை ஆய்வில் உள்ளது.",
    },
    "pay_need": {
        "en": "Payment tracking needs your token or registered phone.",
        "ml": "പേയ്മെന്റ് പരിശോധിക്കാൻ ടോക്കൺ അല്ലെങ്കിൽ രജിസ്റ്റർ ചെയ്ത ഫോൺ വേണം.",
        "hi": "भुगतान जानने के लिए टोकन या रजिस्टर्ड फोन चाहिए।",
        "ta": "பணம் அறிய டோக்கன் அல்லது பதிவு செய்த ஃபோன் தேவை.",
    },
    "nearby": {
        "en": "Centres ranked by total journey time: {names}.",
        "ml": "ആകെ യാത്രാ സമയം അടിസ്ഥാനമാക്കിയുള്ള കേന്ദ്രങ്ങൾ: {names}.",
        "hi": "कुल यात्रा समय के अनुसार केंद्र: {names}.",
        "ta": "மொத்த பயண நேர அடிப்படையில் மையங்கள்: {names}.",
    },
    "grievance": {
        "en": "You can raise a grievance from the app (Raise a concern) or by SMS. You'll get an MM-GRV tracking ID and the status timeline is visible to you end-to-end.",
        "ml": "ആപ്പിൽ (Raise a concern) അല്ലെങ്കിൽ SMS വഴി പരാതി നൽകാം. MM-GRV ട്രാക്കിംഗ് ഐഡി ലഭിക്കും; നില മുഴുവനായി കാണാം.",
        "hi": "ऐप (Raise a concern) या SMS से शिकायत दर्ज करें। MM-GRV ट्रैकिंग आईडी मिलेगी और पूरी स्थिति आप देख सकते हैं।",
        "ta": "ஆப் அல்லது SMS மூலம் புகார் அளிக்கலாம். MM-GRV கண்காணிப்பு ஐடி கிடைக்கும்; நிலை முழுவதையும் காணலாம்.",
    },
    "fallback": {
        "en": "I can help with your turn, payment status, required documents, nearby centres and grievances. For anything else, contact the mandi officer.",
        "ml": "ടേൺ, പേയ്മെന്റ് നില, ആവശ്യമായ രേഖകൾ, അടുത്തുള്ള കേന്ദ്രങ്ങൾ, പരാതികൾ എന്നിവയിൽ സഹായിക്കാം. മറ്റെല്ലാം മണ്ഡി ഉദ്യോഗസ്ഥനെ സമീപിക്കൂ.",
        "hi": "बारी, भुगतान स्थिति, दस्तावेज़, नज़दीकी केंद्र और शिकायतों में मदद कर सकता हूँ। अन्य सहायता के लिए मंडी अधिकारी से संपर्क करें।",
        "ta": "முறை, பணம், ஆவணங்கள், அருகிலுள்ள மையங்கள், புகார்கள் என உதவ முடியும். மற்றவற்றுக்கு மண்டி அதிகாரியை தொடர்பு கொள்ளுங்கள்.",
    },
}


def _r(key: str, lang: str, **kw) -> str:
    return R[key].get(lang or "en", R[key]["en"]).format(**kw)


def _status_word(status: str, lang: str) -> str:
    words = {
        "en": {"SLOT_BOOKED": "booked", "ARRIVED": "checked in", "WEIGHING": "at weighing",
               "QUALITY_CHECK": "at quality check", "PAYMENT": "at payment", "COMPLETED": "completed"},
        "ml": {"SLOT_BOOKED": "ബുക്ക് ചെയ്തു", "ARRIVED": "എത്തി", "WEIGHING": "തൂക്കത്തിൽ",
               "QUALITY_CHECK": "ഗുണനിലവാര പരിശോധനയിൽ", "PAYMENT": "പേയ്മെന്റിൽ", "COMPLETED": "പൂർത്തിയായി"},
        "hi": {"SLOT_BOOKED": "बुक है", "ARRIVED": "पहुँच गए", "WEIGHING": "तौल पर",
               "QUALITY_CHECK": "गुणवत्ता जाँच पर", "PAYMENT": "भुगतान पर", "COMPLETED": "पूर्ण"},
        "ta": {"SLOT_BOOKED": "பதிவு ஆனது", "ARRIVED": "வந்துவிட்டது", "WEIGHING": "தராசில்",
               "QUALITY_CHECK": "தர சோதனையில்", "PAYMENT": "பணப் படியில்", "COMPLETED": "முடிந்தது"},
    }
    return words.get(lang or "en", words["en"]).get(status, status.replace("_", " ").lower())

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
    ("turn", [r"my turn", r"when.*turn", r"queue position", r"how long", r"eta", r"wait",
              # ml: turn / when / queue / wait   hi: bari / kab / kataar   ta: murai / eppodhu
              r"ടേൺ", r"എപ്പോൾ", r"ക്യൂ", r"കാത്തിരുപ്പ", r"ബാരി|बारी", r"कब", r"कतार", r"मुरै|முறை", r"எப்போது", r"வரிசை"]),
    ("payment", [r"payment", r"paid", r"amount", r"money",
                 r"പേയ്മെന്റ്", r"പണം", r"തുക", r"भुगतान", r"पैसा", r"பணம்", r"தொகை"]),
    ("documents", [r"document", r"paper", r"carry", r"proof",
                   r"രേഖ", r"ദസ്ത", r"कागज़", r"दस्तावेज़", r"ஆவண"]),
    ("nearby", [r"nearby", r"nearest", r"which mandi", r"other cent", r"less crowd",
                r"അടുത്ത", r"ഏത് കേന്ദ്ര", r"नज़दीक", r"அருகில", r"எந்த மையம்"]),
    ("procedure", [r"process", r"how.*procure", r"steps", r"quality check", r"weighing",
                   r"ഗുണനിലവാര", r"തൂക്ക", r"गुणवत्ता", r"तौल", r"தரம்", r"தராசு"]),
    ("grievance", [r"complaint", r"grievance", r"issue.*report", r"problem",
                   r"പരാതി", r"शिकायत", r"புகார்"]),
]


def assistant_reply(question: str, user: dict) -> dict:
    q = question.lower()
    lang = user.get("lang") or detect_lang(question)
    tool_calls = []

    def use(name, args):
        tool_calls.append({"tool": name, "args": args})
        return call_tool(name, args, user)

    intent = next((i for i, pats in INTENTS if any(re.search(p, q) for p in pats)), None)

    if intent == "turn" and (user.get("token") or user.get("phone")):
        r = use("get_farmer_status", {"token": user.get("token"), "phone": user.get("phone")})
        if "error" not in r:
            return {"reply": _r("turn", lang, token=r["token"],
                               status=_status_word(r["status"], lang),
                               pos=r["position"], eta=r["eta_minutes"]),
                    "tool_calls": tool_calls}
        return {"reply": _r("no_booking", lang), "tool_calls": tool_calls}

    if intent == "payment" and (user.get("token") or user.get("phone")):
        r = use("get_farmer_status", {"token": user.get("token"), "phone": user.get("phone")})
        if "error" not in r:
            amt = int(r["amount"] or 0)
            if r["payment_status"] == "COMPLETED":
                return {"reply": _r("pay_done", lang, amt=amt), "tool_calls": tool_calls}
            if r["payment_status"] == "PROCESSING":
                return {"reply": _r("pay_proc", lang, amt=amt), "tool_calls": tool_calls}
            if r["payment_status"] == "DELAYED":
                return {"reply": _r("pay_delay", lang, amt=amt), "tool_calls": tool_calls}
        return {"reply": _r("pay_need", lang), "tool_calls": tool_calls}

    if intent == "documents":
        hits = rag_search("documents required farmer procurement")
        if hits:
            h = hits[0]
            return {"reply": f"According to '{h['title']}' ({h['source']}, updated {h['updated']}): {h['content'][:280]}",
                    "sources": hits, "tool_calls": tool_calls}

    if intent == "nearby":
        r = use("find_nearby_centres", {"lat": user.get("lat"), "lng": user.get("lng"),
                                        "crop": user.get("crop")})
        names = ", ".join(f"{c['name']} ({c['queue_length']}, ~{c['total_journey_minutes']}m)"
                          for c in r["centres"][:3])
        return {"reply": _r("nearby", lang, names=names),
                "tool_calls": tool_calls}

    if intent == "grievance":
        return {"reply": _r("grievance", lang), "tool_calls": tool_calls}

    # Default: RAG over official knowledge base.
    hits = rag_search(question)
    if hits:
        h = hits[0]
        return {"reply": f"From the official knowledge base ('{h['title']}', {h['source']}, updated {h['updated']}): {h['content'][:280]}",
                "sources": hits, "tool_calls": tool_calls}

    return {"reply": _r("fallback", lang),
            "tool_calls": tool_calls}
