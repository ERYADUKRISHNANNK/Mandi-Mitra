"""Multilingual farmer-facing message templates.

Languages: en (English), ml (Malayalam), hi (Hindi), ta (Tamil).
The IVR layer reads the same templates aloud through the simulated gateway.
"""

TEMPLATES: dict[str, dict[str, str]] = {
    "IVR_MENU_CROPS": {
        "en": "Welcome to Mandi Mitra. For Paddy, press 1. For Wheat, press 2. For other crops, press 3.",
        "ml": "മണ്ഡി മിത്രയിലേക്ക് സ്വാഗതം. നെല്ലിന് 1 അമർത്തുക. ഗോതമ്പിന് 2. മറ്റ് വിളകൾക്ക് 3.",
        "hi": "मंडी मित्र में आपका स्वागत है। धान के लिए 1 दबाएँ। गेहूँ के लिए 2। अन्य फसलों के लिए 3।",
        "ta": "மண்டி மித்ராவுக்கு வரவேற்கிறோம். நெல்லுக்கு 1 அழுத்துங்கள். கோதுமைக்கு 2. மற்ற பயிர்களுக்கு 3.",
        "pa": "ਮੰਡੀ ਮਿੱਤਰ ਵਿੱਚ ਜੀ ਆਇਆਂ ਨੂੰ। ਝੋਨੇ ਲਈ 1 ਦਬਾਓ। ਕਣਕ ਲਈ 2। ਹੋਰ ਫ਼ਸਲਾਂ ਲਈ 3।",
        "mr": "मंडी मित्रमध्ये स्वागत आहे. भातासाठी 1 दाबा. गहूसाठी 2. इतर पीकांसाठी 3.",
        "te": "మండి మిత్రుడికి స్వాగతం. వరికి 1 నొక్కండి. గోధుమలకు 2. ఇతర పంటలకు 3.",
        "kn": "ಮಂಡಿ ಮಿತ್ರಕ್ಕೆ ಸ್ವಾಗತ. ಭತ್ತಕ್ಕೆ 1 ಒತ್ತಿ. ಗೋಧಿಗೆ 2. ಇತರ ಬೆಳೆಗಳಿಗೆ 3.",
        "bn": "মণ্ডি মিত্রে স্বাগতম। ধানের জন্য 1 চাপুন। গমের জন্য 2। অন্য ফসলের জন্য 3।",
        "gu": "માંડી મિત્રમાં આપનું સ્વાગત છે. ડાંગર માટે 1 દબાવો. ઘઉં માટે 2. અન્ય પાક માટે 3.",
    },
    "IVR_ASK_QUANTITY": {
        "en": "How many bags are you bringing? Enter the number on your keypad, then press the hash key.",
        "ml": "എത്ര സഞ്ചികൾ കൊണ്ടുവരുന്നു? കീപാഡിൽ സംഖ്യ അമർത്തി, ഹാഷ് കീ അമർത്തുക.",
        "hi": "आप कितनी बोरियाँ ला रहे हैं? कीपैड पर संख्या दबाएँ, फिर हैश दबाएँ।",
        "ta": "எத்தனை பை கொண்டு வருகிறீர்கள்? கீபேட்டில் எண்ணை அழுத்தி, ஹேஷ் விசையை அழுத்துங்கள்.",
        "pa": "ਤੁਸੀਂ ਕਿੰਨੀਆਂ ਬੋਰੀਆਂ ਲਿਆ ਰਹੇ ਹੋ? ਕੀਪੈਡ 'ਤੇ ਗਿਣਤੀ ਦਬਾਓ, ਫਿਰ ਹੈਸ਼ ਦਬਾਓ।",
        "mr": "तुम्ही किती बोरी आणताय? कीपॅडवर संख्या दाबा, मग हॅश दाबा.",
        "te": "ఎన్ని బస్తాలు తెస్తున్నారు? కీప్యాడ్‌లో సంఖ్య నొక్కి, హ్యాష్ నొక్కండి.",
        "kn": "ಎಷ್ಟು ಚೀಲ ತರುತ್ತಿದ್ದೀರಿ? ಕೀಪ್ಯಾಡ್‌ನಲ್ಲಿ ಸಂಖ್ಯೆ ಒತ್ತಿ, ನಂತರ ಹ್ಯಾಶ್ ಒತ್ತಿ.",
        "bn": "কত বস্তা আনছেন? কিপ্যাডে সংখ্যা চাপুন, তারপর হ্যাশ চাপুন।",
        "gu": "કેટલી બોરીઓ લાવો છો? કીપેડ પર નંબર દબાવો, પછી હેશ દબાવો.",
    },
    "IVR_BOOKED": {
        "en": "Your token is {token}. Please reach {name} by {time}. An SMS with details is on its way.",
        "ml": "നിങ്ങളുടെ ടോക്കൺ {token}. {name}-യിൽ {time}-യ്ക്ക് മുൻപ് എത്തുക. വിവരങ്ങളുള്ള SMS വരുന്നു.",
        "hi": "आपका टोकन {token} है। कृपया {time} तक {name} पहुँचें। विवरण के साथ SMS भेजा जा रहा है।",
        "ta": "உங்கள் டோக்கன் {token}. {time} மண்ணுக்குள் {name} வந்தடையுங்கள். விவரங்களுடன் SMS அனுப்பப்படுகிறது.",
        "pa": "ਤੁਹਾਡਾ ਟੋਕਨ {token} ਹੈ। ਕਿਰਪਾ ਕਰਕੇ {time} ਤੱਕ {name} ਪਹੁੰਚੋ। ਵੇਰਵਿਆਂ ਸਮੇਤ SMS ਭੇਜਿਆ ਜਾ ਰਿਹਾ ਹੈ।",
        "mr": "तुमचे टोकन {token} आहे. कृपया {time} पर्यंत {name} येथे पोहोचा. तपशीलासह SMS पाठवत आहोत.",
        "te": "మీ టోకెన్ {token}. దయచేసి {time} లోపు {name} చేరుకోండి. వివరాలతో SMS పంపుతున్నాము.",
        "kn": "ನಿಮ್ಮ ಟೋಕನ್ {token}. ದಯವಿಟ್ಟು {time} ಒಳಗೆ {name} ತಲುಪಿ. ವಿವರಗಳೊಂದಿಗೆ SMS ಕಳುಹಿಸಲಾಗುತ್ತಿದೆ.",
        "bn": "আপনার টোকেন {token}। অনুগ্রহ করে {time} এর মধ্যে {name} পৌঁছান। বিবরণ সহ SMS পাঠানো হচ্ছে।",
        "gu": "તમારું ટોકન {token} છે. કૃપા કરીને {time} સુધીમાં {name} પહોંચો. વિગતો સાથે SMS મોકલી રહ્યા છીએ.",
    },
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
        "pa": "ਮੰਡੀ ਮਿੱਤਰ: ਹੁਣੇ ਘਰੋਂ ਨਿਕਲੋ। ਟੋਕਨ {token}। ਅਨੁਮਾਨਿਤ ਵਾਰੀ {eta_time}। ਕਤਾਰ ਵਿੱਚ {position} ਸਥਾਨ।",
        "mr": "मंडी मित्र: आत्ता घरी निघा. टोकन {token}. अपेक्षित वेळ {eta_time}. रांगेत {position} स्थान.",
        "te": "మండి మిత్ర: ఇప్పుడే ఇంటి నుండి బయలుదేరండి. టోకెన్ {token}. అంచనా వేళ {eta_time}. క్యూలో {position} స్థానం.",
        "kn": "ಮಂಡಿ ಮಿತ್ರ: ಈಗಲೇ ಮನೆಯಿಂದ ಹೊರಡಿ. ಟೋಕನ್ {token}. ನಿರೀಕ್ಷಿತ ಸಮಯ {eta_time}. ಸಾಲಿನಲ್ಲಿ {position} ಸ್ಥಾನ.",
        "bn": "মণ্ডি মিত্র: এখনই ঘর থেকে বের হন। টোকেন {token}। প্রত্যাশিত সময় {eta_time}। লাইনে {position} স্থান।",
        "gu": "માંડી મિત્ર: હવે ઘરેથી નીકળો. ટોકન {token}. અપેક્ષિત સમય {eta_time}. કતારમાં {position} સ્થાન.",
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


SUPPORTED_LANGS = ["en", "ml", "hi", "ta", "pa", "mr", "te", "kn", "bn", "gu"]
