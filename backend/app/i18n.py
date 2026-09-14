"""Multilingual farmer-facing message templates.

Languages: en (English), ml (Malayalam), hi (Hindi), ta (Tamil).
The IVR layer reads the same templates aloud through the simulated gateway.
"""

TEMPLATES: dict[str, dict[str, str]] = {
    "BOOKING_CONFIRMED": {
        "en": "Mandi Mitra: Booking confirmed. Token {token} for {crop} at {date} {time}. Track your turn on the app, SMS or missed call.",
        "ml": "മണ്ഡി മിത്ര: ബുക്കിംഗ് സ്ഥിരീകരിച്ചു. ടോക്കൺ {token}, {crop}, {date} {time}. നിങ്ങളുടെ ടേൺ ആപ്പിലോ SMS-ലോ അറിയാം.",
        "hi": "मंडी मित्र: बुकिंग हो गई। टोकन {token}, {crop}, {date} {time}। अपनी बारी ऐप/SMS से जानें।",
        "ta": "மண்டி மித்ரா: முன்பதிவு உறுதி. டோக்கன் {token}, {crop}, {date} {time}. உங்கள் முறையை அப்பில் தெரிந்துகொள்ளுங்கள்.",
    },
    "ARRIVAL_CONFIRMED": {
        "en": "Mandi Mitra: Arrival verified. Token {token} is now in the live queue. Position: {position}. Est. wait: {eta} min.",
        "ml": "മണ്ഡി മിത്ര: എത്തിച്ചേർന്നത് രേഖപ്പെടുത്തി. ടോക്കൺ {token} ലൈവ് ക്യൂവിൽ. സ്ഥാനം {position}. പ്രതീക്ഷിക്കുന്നത് {eta} മിനിറ്റ്.",
        "hi": "मंडी मित्र: आवागमन दर्ज। टोकन {token} लाइव कतार में। स्थान {position}। अनुमानित {eta} मिनट।",
        "ta": "மண்டி மித்ரா: வருகை பதிவு. டோக்கன் {token} நேரடி வரிசையில். இடம் {position}. காத்திருப்பு {eta} நிமிடம்.",
    },
    "LEAVE_HOME": {
        "en": "Mandi Mitra: LEAVE HOME NOW. Token {token}. Est. turn at {eta_time}. Current position {position}. Queue moving fast.",
        "ml": "മണ്ഡി മിത്ര: ഇപ്പോൾ പുറപ്പെടുക. ടോക്കൺ {token}. പ്രതീക്ഷിക്കുന്ന ടേൺ {eta_time}. നിരയിൽ {position} സ്ഥാനം.",
        "hi": "मंडी मित्र: अब घर से निकलें। टोकन {token}। अनुमानित बारी {eta_time}। स्थान {position}।",
        "ta": "மண்டி மித்ரா: இப்போது கிளம்புங்கள். டோக்கன் {token}. எதிர்பார்க்கும் முறை {eta_time}. இடம் {position}.",
    },
    "TURN_SOON": {
        "en": "Mandi Mitra: Your turn is approaching! Token {token}. Only {position} farmer(s) ahead. Please be at the centre.",
        "ml": "മണ്ഡി മിത്ര: നിങ്ങളുടെ ടേൺ സമീപിക്കുന്നു! ടോക്കൺ {token}. മുന്നിൽ {position} പേർ മാത്രം. കേന്ദ്രത്തിൽ ഉണ്ടാകൂ.",
        "hi": "मंडी मित्र: आपकी बारी नज़दीक है! टोकन {token}। आपसे पहले केवल {position} किसान। केंद्र पर रहें।",
        "ta": "மண்டி மித்ரா: உங்கள் முறை நெருங்குகிறது! டோக்கன் {token}. முன் {position} பேர் மட்டும். மையத்தில் இருங்கள்.",
    },
    "WEIGHING_STARTED": {
        "en": "Mandi Mitra: Weighing started for token {token} at counter {counter}.",
        "ml": "മണ്ഡി മിത്ര: ടോക്കൺ {token} തൂക്കം ആരംഭിച്ചു, കൗണ്ടർ {counter}.",
        "hi": "मंडी मित्र: टोकन {token} की तौल शुरू, काउंटर {counter}।",
        "ta": "மண்டி மித்ரா: டோக்கன் {token} தராசு தொடங்கியது, கவுண்டர் {counter}.",
    },
    "QUALITY_CHECK": {
        "en": "Mandi Mitra: Quality verification in progress for token {token}. Grade {grade}. Procurement amount ₹{amount}.",
        "ml": "മണ്ഡി മിത്ര: ടോക്കൺ {token} ഗുണനിലവാര പരിശോധന. ഗ്രേഡ് {grade}. തുക ₹{amount}.",
        "hi": "मंडी मित्र: टोकन {token} गुणवत्ता जांच। ग्रेड {grade}। राशि ₹{amount}।",
        "ta": "மண்டி மித்ரா: டோக்கன் {token} தரச் சோதனை. தரம் {grade}. தொகை ₹{amount}.",
    },
    "PAYMENT_INITIATED": {
        "en": "Mandi Mitra: Payment of ₹{amount} initiated for token {token}. You will be notified on completion.",
        "ml": "മണ്ഡി മിത്ര: ടോക്കൺ {token} ₹{amount} പേയ്മെന്റ് ആരംഭിച്ചു. പൂർത്തിയാകുമ്പോൾ അറിയിക്കും.",
        "hi": "मंडी मित्र: टोकन {token} का ₹{amount} भुगतान शुरू। पूरा होने पर सूचना मिलेगी।",
        "ta": "மண்டி மித்ரா: டோக்கன் {token} ₹{amount} பணம் தொடங்கியது. முடிந்ததும் தெரிவிக்கப்படும்.",
    },
    "PAYMENT_RECEIVED": {
        "en": "Mandi Mitra: ₹{amount} received for token {token}. Procurement complete. Thank you!",
        "ml": "മണ്ഡി മിത്ര: ടോക്കൺ {token} ₹{amount} സ്വീകരിച്ചു. വാങ്ങൽ പൂർത്തിയായി. നന്ദി!",
        "hi": "मंडी मित्र: टोकन {token} का ₹{amount} प्राप्त। खरीद पूरी। धन्यवाद!",
        "ta": "மண்டி மித்ரா: டோக்கன் {token} ₹{amount} பெறப்பட்டது. கொள்முதல் முடிந்தது. நன்றி!",
    },
    "NO_SHOW_REMINDER": {
        "en": "Mandi Mitra: You missed your slot (token {token}). Contact staff or re-check in to rejoin the queue.",
        "ml": "മണ്ഡി മിത്ര: നിങ്ങൾ എത്തിയില്ല (ടോക്കൺ {token}). വീണ്ടും ചേരാൻ ജീവനക്കാരുമായി ബന്ധപ്പെടൂ.",
        "hi": "मंडी मित्र: आप केंद्र नहीं आए (टोकन {token})। पुनः जुड़ने के लिए स्टाफ से संपर्क करें।",
        "ta": "மண்டி மித்ரா: நீங்கள் வரவில்லை (டோக்கன் {token}). மீண்டும் இணைய ஊழியரை தொடர்பு கொள்ளுங்கள்.",
    },
    "CONGESTION_AHEAD": {
        "en": "Mandi Mitra: Heavy rush expected at {mandi} around your slot. Stay home — we'll tell you exactly when to start. Or consider {alt}.",
        "ml": "മണ്ഡി മിത്ര: നിങ്ങളുടെ സ്ലോട്ട് സമയത്ത് {mandi}-ൽ തിരക്ക് പ്രതീക്ഷിക്കുന്നു. വീട്ടിൽ തുടരൂ — എപ്പോൾ ഇറങ്ങണമെന്ന് അറിയിക്കാം. {alt} പരിഗണിക്കാം.",
        "hi": "मंडी मित्र: आपके स्लॉट के समय {mandi} में भीड़ संभव है। घर पर रहें — सही समय पर सूचना देंगे। {alt} भी देखें।",
        "ta": "மண்டி மித்ரா: உங்கள் நேரத்தில் {mandi} நெரிசல் எதிர்பார்க்கப்படுகிறது. வீட்டில் இருங்கள் — எப்போது கிளம்ப வேண்டும் என்று சொல்கிறோம். {alt} பார்க்கலாம்.",
    },
    "PAYMENT_DELAY": {
        "en": "Mandi Mitra: Payment for token {token} is delayed beyond the expected window. Our team is reviewing it.",
        "ml": "മണ്ഡി മിത്ര: ടോക്കൺ {token} പേയ്മെന്റ് പ്രതീക്ഷിച്ച സമയത്തിനപ്പുറം വൈകി. ടീം പരിശോധിക്കുന്നു.",
        "hi": "मंडी मित्र: टोकन {token} का भुगतान विलंबित है। टीम समीक्षा कर रही है।",
        "ta": "மண்டி மித்ரா: டோக்கன் {token} பணம் தாமதமாகிறது. குழு மறுஆய்வு செய்கிறது.",
    },
}


def render(lang: str, template_key: str, ctx: dict | None = None) -> str:
    template = TEMPLATES.get(template_key, {}).get(lang) or TEMPLATES.get(template_key, {}).get("en", template_key)
    ctx = ctx or {}
    try:
        return template.format(**ctx)
    except (KeyError, IndexError):
        return template


SUPPORTED_LANGS = ["en", "ml", "hi", "ta"]
