"""Spoken-language NLU for voice-to-action booking.

Parses a farmer's natural request — English, Malayalam, Hindi or Tamil —
into structured booking intent: crop, quantity (kg or bags), day and
time-of-day. Farmers don't speak in form fields; this understands the words
they actually say, in any of the four supported languages, without grammar.
"""

import re

from .assistant import detect_lang

# ---- vocabulary (recognise, don't translate — farmers mix languages) ------- #

CROP_WORDS = {
    "Paddy": ["paddy", "rice", "നെല്ല്", "നെല്ല", "അരി", "நெல்", "நெல்லு",
              "धान", "चावल", "झोना", "ਧਾਨ", "भात", "వరి", "ధాన్యం",
              "ಭತ್ತ", "ধান", "ડાંગર"],
    "Wheat": ["wheat", "ഗോതമ്പ്", "गेहूं", "गेहूँ", "கோதுமை", "ਕਣਕ",
              "गहू", "గోధుమ", "ಗೋಧಿ", "গম", "ઘઉં"],
    "Maize": ["maize", "corn", "ചോളം", "मक्का", "மக்காச்சோளம்", "மக்கா",
              "ਮੱਕੀ", "मका", "మొక్కజొన్న", "ಜೋಳ", "ভুট্টা", "મકાઈ"],
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100,
    "ഒന്ന്": 1, "രണ്ട്": 2, "മൂന്ന്": 3, "നാല്": 4, "അഞ്ച്": 5, "ആറ്": 6,
    "പത്ത്": 10, "ഇരുപത്": 20, "മുപ്പത്": 30, "നാല്പത്": 40, "അമ്പത്": 50,
    "നൂറ്": 100, "ആയിരം": 1000,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "दस": 10,
    "बीस": 20, "तीस": 30, "पचास": 50, "सौ": 100, "हज़ार": 1000,
    "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5,
    "பத்து": 10, "இருபது": 20, "ஐம்பது": 50, "நூறு": 100, "ஆயிரம்": 1000,
}

BAG_WORDS = ["bag", "bags", "sack", "sacks", "സഞ്ചി", "സഞ്ചികൾ", "ചാക്ക്",
             "ചാക്ക", "बोरी", "बोरियाँ", "பை", "சாக்கு", "ਬੋਰੀ", "ਬੋਰੀਆਂ",
             "बोरी", "झोले", "బస్తా", "బస్తాలు", "ಚೀಲ", "ಚೀಲಗಳು", "বস্তা",
             "বস্তাগুলি", "બોરી", "બોરીઓ"]
KG_WORDS = ["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms",
            "കിലോ", "കിലോഗ്രാം", "किलो", "किलोग्राम", "கிலோ", "கிலோகிராம்",
            "ਕਿਲੋ", "కిలోలు", "కేజీ", "ಕೆಜಿ", "ಕಿಲೋ", "কেজি", "কিলো", "કિલો"]
BAG_KG = 50.0  # standard procurement bag assumption, shown to the farmer

MORNING_WORDS = ["morning", "രാവിലെ", "പ്രഭാതം", "सुबह", "प्रातः", "காலை",
                 "ਸਵੇਰੇ", "ਸਵੇਰ", "सकाळी", "ఉదయం", "ಬೆಳಿಗ್ಗೆ", "সকাল", "સવારે"]
AFTERNOON_WORDS = ["afternoon", "noon", "ഉച്ച", "दोपहर", "மத்தியானம்",
                   "ਦੁਪਹਿਰ", "మధ్యాహ్నం", "ಮಧ್ಯಾಹ್ನ", "দুপুর", "બપોરે"]
EVENING_WORDS = ["evening", "വൈകുന്നേരം", "സന്ധ്യ", "शाम", "संध्या", "மாலை",
                 "ਸ਼ਾਮ", "संध्याकाळी", "సాయంత్రం", "ಸಂಜೆ", "সন্ধ্যা", "સાંજે"]
TODAY_WORDS = ["today", "ഇന്ന്", "इंटू", "आज", "இன்று", "இன்னைக்கு",
               "ਅੱਜ", "ఈరోజు", "ಇಂದು", "আজ", "આજે"]
TOMORROW_WORDS = ["tomorrow", "നാളെ", "नाळെ", "कल", "நாளை", "நாளைக்கு",
                  "ਕੱਲ੍ਹ", "ਕਲ", "उद्या", "రేపు", "ನಾಳೆ", "আগামীকাল", "કાલે", "કાલ"]


def _find_any(text: str, words: list[str]) -> str | None:
    for w in words:
        if w in text:
            return w
    return None


TIME_UNIT_WORDS = ["മണിക്ക്", "മണി", "बजे", "மணி", "o'clock", "o clock",
                   "ਵਜੇ", "वाजता", "గంటకు", "ಗಂಟೆಗೆ", "টায়", "વાગ્યે"]


def _numbers(s: str):
    """Yield (value, match) for digit numbers first, then number-words."""
    for m in re.finditer(r"(\d+(?:\.\d+)?)", s):
        yield float(m.group(1)), m
    for w, v in NUMBER_WORDS.items():
        for m in re.finditer(rf"(?<!\w){re.escape(w)}(?!\w)", s):
            yield float(v), m


def _classify(t: str, m) -> str:
    """Classify a number by the NEAREST unit word that follows it
    (handles "4 बजे 10 बोरी" where a bag word also appears further off)."""
    tail = t[m.end(): m.end() + 18]
    best, best_idx = "", 10**9
    for kind, words in (("kg", KG_WORDS), ("bags", BAG_WORDS), ("time", TIME_UNIT_WORDS)):
        for w in words:
            idx = tail.find(w)
            if 0 <= idx < best_idx:
                best, best_idx = kind, idx
    if best:
        return best
    return "time" if re.match(r"\s*(am|pm|a\.m|p\.m)", tail) else ""


def parse(text: str) -> dict:
    """Extract {crop, quantity_kg, day, time, lang} from one sentence."""
    t = (text or "").lower()
    out = {"crop": None, "quantity_kg": None, "quantity_source": None,
           "day": None, "time": None, "lang": detect_lang(text or "") or "en"}

    for crop, words in CROP_WORDS.items():
        if _find_any(t, words):
            out["crop"] = crop
            break

    # ---- classify every number by the unit word that follows it ----------- #
    qty = None          # (value, match)
    qty_bare = None     # first bare number in a plausible kg range
    tmatch = None       # time number
    for v, m in _numbers(t):
        kind = _classify(t, m)
        if kind == "kg" and qty is None:
            qty = (v, m)
        elif kind == "bags" and qty is None:
            qty = (v, m)
        elif kind == "time" and tmatch is None:
            tmatch = m
        elif not kind:
            if qty_bare is None and 5 <= v <= 20000:
                qty_bare = (v, m)
            if tmatch is None and 1 <= v <= 12:
                tmatch = m          # "3" alone may still be an hour
    if qty is None:
        qty = qty_bare

    if qty is not None:
        v, m = qty
        kind = _classify(t, m)
        if kind == "bags":
            out["quantity_kg"] = v * BAG_KG
            out["quantity_source"] = f"{int(v)} bags × {int(BAG_KG)} kg"
        else:
            out["quantity_kg"] = v
            out["quantity_source"] = "spoken"

    # ---- time -------------------------------------------------------------- #
    minute = 0
    mer = ""
    morning = _find_any(t, MORNING_WORDS) is not None
    evening = _find_any(t, EVENING_WORDS) is not None
    afternoon = _find_any(t, AFTERNOON_WORDS) is not None
    hour = None
    if tmatch is not None:
        txt = tmatch.group(0)
        if txt.isdigit():
            hm = re.match(r"(\d{1,2})(?::(\d{2}))?", txt)
            hour = int(hm.group(1))
            minute = int(hm.group(2) or 0)
        else:
            hour = int(NUMBER_WORDS.get(txt, 0)) or None
    if hour is None and (morning or afternoon or evening):
        hour, mer = (9, "") if morning else (13, "") if afternoon else (17, "")
    if hour is not None:
        if mer == "pm" and hour < 12:
            hour += 12
        elif mer == "am" and hour == 12:
            hour = 0
        elif not mer:
            if (evening or afternoon) and hour < 12:
                hour += 12
            elif not morning and 1 <= hour <= 8:
                hour += 12   # procurement hours: bare "3" means afternoon
        if 0 <= hour <= 23:
            out["time"] = f"{hour:02d}:{minute:02d}"

    # ---- day -------------------------------------------------------------- #
    if _find_any(t, TOMORROW_WORDS):
        out["day"] = "tomorrow"
    elif _find_any(t, TODAY_WORDS) or out["time"]:
        out["day"] = "today"      # "at 3 pm" means today unless tomorrow said
    return out


MSG = {
    "proposal": {
        "en": "{name} has a {slot} slot {when}. Understood: {crop}, {qty} kg. Shall I book it? Say yes to confirm.",
        "ml": "{name}-ൽ {slot} സ്ലോട്ട് {when} ഉണ്ട്. മനസ്സിലായി: {crop}, {qty} കിലോ. ബുക്ക് ചെയ്യട്ടെ? സമ്മതിക്കാൻ 'അതെ' എന്ന് പറയൂ.",
        "hi": "{name} में {slot} स्लॉट {when} उपलब्ध है। समझ गया: {crop}, {qty} किलो। बुक कर दूँ? हाँ कहकर पुष्टि करें।",
        "ta": "{name}-இல் {slot} ஸ்லாட் {when} உள்ளது. புரிந்தது: {crop}, {qty} கிலோ. பதிவு செய்யவா? 'ஆம்' என்று சொல்லுங்கள்.",
        "pa": "{name} ਵਿੱਚ {slot} ਸਲਾਟ {when} ਉਪਲਬਧ ਹੈ। ਸਮਝ ਗਏ: {crop}, {qty} ਕਿਲੋ। ਬੁੱਕ ਕਰਾਂ? 'ਹਾਂ' ਕਹਿ ਕੇ ਪੱਕਾ ਕਰੋ।",
        "mr": "{name} येथे {slot} स्लॉट {when} उपलब्ध आहे. समजले: {crop}, {qty} किलो. बुक करू का? 'हो' म्हणून खात्री करा.",
        "te": "{name} లో {slot} స్లాట్ {when} అందుబాటులో ఉంది. అర్థమైంది: {crop}, {qty} కిలోలు. బుక్ చేయాలా? 'అవును' అని ఖరారు చేయండి.",
        "kn": "{name} ನಲ್ಲಿ {slot} ಸ್ಲಾಟ್ {when} ಲಭ್ಯವಿದೆ. ಅರ್ಥವಾಯಿತು: {crop}, {qty} ಕೆಜಿ. ಬುಕ್ ಮಾಡಬೇಕೆ? 'ಹೌದು' ಎಂದು ದೃಢೀಕರಿಸಿ.",
        "bn": "{name} এ {slot} স্লট {when} উপলব্ধ। বুঝেছি: {crop}, {qty} কেজি। বুক করব? 'হ্যাঁ' বলে নিশ্চিত করুন।",
        "gu": "{name} માં {slot} સ્લોટ {when} ઉપલબ્ધ છે. સમજાઈ ગયું: {crop}, {qty} કિલો. બુક કરું? 'હા' કહીને પુષ્ટિ કરો.",
    },
    "no_crop": {
        "en": "Which crop are you bringing, and roughly how much? For example: \"20 bags of paddy today 3 pm\".",
        "ml": "ഏത് വിളയാണ് കൊണ്ടുവരുന്നത്, ഏകദേശം എത്ര? ഉദാഹരണം: \"ഇന്ന് 3 മണിക്ക് 20 സഞ്ചി നെല്ല്\".",
        "hi": "आप कौन सी फसल ला रहे हैं और लगभग कितनी? उदाहरण: \"आज 3 बजे 20 बोरी धान\"।",
        "ta": "எந்த பயிரை கொண்டு வருகிறீர்கள், சுமார் எவ்வளவு? எடுத்துக்காட்டு: \"இன்று 3 மணி 20 பை நெல்\".",
        "pa": "ਤੁਸੀਂ ਕਿਹੜੀ ਫ਼ਸਲ ਲਿਆ ਰਹੇ ਹੋ, ਤਕਰੀਬਨ ਕਿੰਨੀ? ਮਿਸਾਲ: \"ਅੱਜ 3 ਵਜੇ 20 ਬੋਰੀ ਝੋਨਾ\"।",
        "mr": "तुम्ही कोणते पीक आणताय, जवळपास किती? उदाहरण: \"आज 3 ला 20 झोले भात\".",
        "te": "మీరు ఏ పంట తెస్తున్నారు, సుమారు ఎంత? ఉదాహరణ: \"ఈరోజు 3 గంటకు 20 బస్తాలు వరి\".",
        "kn": "ನೀವು ಯಾವ ಬೆಳೆ ತರುತ್ತಿದ್ದೀರಿ, ಸುಮಾರು ಎಷ್ಟು? ಉದಾಹರಣೆ: \"ಇಂದು 3 ಗಂಟೆಗೆ 20 ಚೀಲ ಭತ್ತ\".",
        "bn": "আপনি কোন ফসল আনছেন, প্রায় কত? উদাহরণ: \"আজ 3 টায় 20 বস্তা ধান\"।",
        "gu": "તમે કયો પાક લાવો છો, આશરે કેટલો? ઉદાહરણ: \"આજે 3 વાગ્યે 20 બોરી ડાંગર\".",
    },
    "unavailable": {
        "en": "No open centres right now. Please try again a little later.",
        "ml": "ഇപ്പോൾ തുറന്ന കേന്ദ്രങ്ങളില്ല. കുറച്ചുകൂടി ശ്രമിക്കൂ.",
        "hi": "अभी कोई खुला केंद्र नहीं है। थोड़ी देर बाद प्रयास करें।",
        "ta": "இப்போது திறந்த மையங்கள் இல்லை. சற்று கழித்து முயற்சிக்கவும்.",
        "pa": "ਇਸ ਸਮੇਂ ਕੋਈ ਖੁੱਲ੍ਹਾ ਕੇਂਦਰ ਨਹੀਂ ਹੈ। ਥੋੜ੍ਹੀ ਦੇਰ ਬਾਅਦ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "mr": "सध्या कोणतेही केंद्र खुले नाही. थोड्या वेळाने पुन्हा प्रयत्न करा.",
        "te": "ప్రస్తుతం తెరిచిన కేంద్రాలు లేవు. కాసేపు తర్వాత ప్రయత్నించండి.",
        "kn": "ಈಗ ಯಾವುದೇ ಕೇಂದ್ರ ತೆರೆದಿಲ್ಲ. ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಪ್ರಯತ್ನಿಸಿ.",
        "bn": "এই মুহূর্তে কোনো খোলা কেন্দ্র নেই। একটু পরে আবার চেষ্টা করুন।",
        "gu": "અત્યારે કોઈ ખુલ્લું કેન્દ્ર નથી. થોડી વાર પછી ફરી પ્રયાસ કરો.",
    },
}


def when_phrase(day: str | None, time: str | None, lang: str) -> str:
    if lang == "ml":
        return "ഇന്ന്" if day == "today" else "നാളെ"
    if lang == "hi":
        return "आज" if day == "today" else "कल"
    if lang == "ta":
        return "இன்று" if day == "today" else "நாளை"
    return "today" if day == "today" else "tomorrow"


def say(key: str, lang: str, **kw) -> str:
    return MSG[key][lang].format(**kw)
