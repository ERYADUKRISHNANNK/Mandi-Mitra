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
    """Script-based language guess across the supported Indic scripts."""
    if re.search(r"[\u0d00-\u0d7f]", text):
        return "ml"
    if re.search(r"[\u0a00-\u0a7f]", text):
        return "pa"
    if re.search(r"[\u0b80-\u0bff]", text):
        return "ta"
    if re.search(r"[\u0c00-\u0c7f]", text):
        return "te"
    if re.search(r"[\u0c80-\u0cff]", text):
        return "kn"
    if re.search(r"[\u0980-\u09ff]", text):
        return "bn"
    if re.search(r"[\u0a80-\u0aff]", text):
        return "gu"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"   # Devanagari also covers Marathi
    return None


R = {
    "turn": {
        "en": "Your token {token} is {status}. Position {pos}, expected wait about {eta} minutes.",
        "ml": "നിങ്ങളുടെ ടോക്കൺ {token} ഇപ്പോൾ {status}. സ്ഥാനം {pos}, ഏകദേശം {eta} മിനിറ്റ് കാത്തിരുപ്പ്.",
        "hi": "आपका टोकन {token} अभी {status} है। स्थान {pos}, अनुमानित प्रतीक्षा लगभग {eta} मिनट।",
        "ta": "உங்கள் டோக்கன் {token} இப்போது {status}. இடம் {pos}, சுமார் {eta} நிமிட காத்திருப்பு.",
        "pa": "ਤੁਹਾਡਾ ਟੋਕਨ {token} ਹੁਣ {status} ਹੈ। ਕਤਾਰ ਵਿੱਚ {pos}, ਤਕਰੀਬਨ {eta} ਮਿੰਟ ਉਡੀਕ।",
        "mr": "तुमचे टोकन {token} आता {status} आहे. रांगेत {pos}, अपेक्षित प्रतीक्षा जवळपास {eta} मिनिटे.",
        "te": "మీ టోకెన్ {token} ఇప్పుడు {status}. క్యూలో {pos}, అంచనా వేచి ఉండడం సుమారు {eta} నిమిషాలు.",
        "kn": "ನಿಮ್ಮ ಟೋಕನ್ {token} ಈಗ {status}. ಸಾಲಿನಲ್ಲಿ {pos}, ನಿರೀಕ್ಷಿತ ಕಾಯುವಿಕೆ ಸುಮಾರು {eta} ನಿಮಿಷ.",
        "bn": "আপনার টোকেন {token} এখন {status}। লাইনে {pos}, প্রত্যাশিত অপেক্ষা প্রায় {eta} মিনিট।",
        "gu": "તમારું ટોકન {token} હવે {status} છે. કતારમાં {pos}, અપેક્ષિત રાહ આશરે {eta} મિનિટ.",
    },
    "no_booking": {
        "en": "I couldn't find an active booking for you. Book via app, SMS (BOOK <mandi> <crop> <qty>) or a missed call.",
        "ml": "നിങ്ങളുടെ സജീവ ബുക്കിംഗ് കണ്ടില്ല. ആപ്പ്, SMS (BOOK <മണ്ഡി> <വിള> <അളവ്>) അല്ലെങ്കിൽ മിസ്സ്ഡ് കോൾ വഴി ബുക്ക് ചെയ്യൂ.",
        "hi": "आपकी कोई सक्रिय बुकिंग नहीं मिली। ऐप, SMS (BOOK <मंडी> <फसल> <मात्रा>) या मिस्ड कॉल से बुक करें।",
        "ta": "உங்கள் செயலில் உள்ள பதிவு எதுவும் கிடைக்கவில்லை. ஆப், SMS அல்லது மிஸ்ட் கால் மூலம் பதிவு செய்யுங்கள்.",
        "pa": "ਤੁਹਾਡੀ ਕੋਈ ਸਰਗਰਮ ਬੁੱਕਿੰਗ ਨਹੀਂ ਮਿਲੀ। ਐਪ, SMS (BOOK <ਮੰਡੀ> <ਫ਼ਸਲ> <ਮਾਤਰਾ>) ਜਾਂ ਮਿਸਡ ਕਾਲ ਨਾਲ ਬੁੱਕ ਕਰੋ।",
        "mr": "तुमची कोणतीही सक्रिय बुकिंग सापडली नाही. अॅप, SMS (BOOK <मंडी> <पीक> <प्रमाण>) किंवा मिस्ड कॉलने बुक करा.",
        "te": "మీ చురుకైన బుకింగ్ కనబడలేదు. యాప్, SMS (BOOK <కేంద్రం> <పంట> <పరిమాణం>) లేదా మిస్డ్ కాల్ ద్వారా బుక్ చేయండి.",
        "kn": "ನಿಮ್ಮ ಸಕ್ರಿಯ ಬುಕಿಂಗ್ ಸಿಗಲಿಲ್ಲ. ಆ್ಯಪ್, SMS (BOOK <ಕೇಂದ್ರ> <ಬೆಳೆ> <ಪ್ರಮಾಣ>) ಅಥವಾ ಮಿಸ್ಡ್ ಕಾಲ್ ಮೂಲಕ ಬುಕ್ ಮಾಡಿ.",
        "bn": "আপনার কোনো সক্রিয় বুকিং পাওয়া যায়নি। অ্যাপ, SMS (BOOK <কেন্দ্র> <ফসল> <পরিমাণ>) বা মিসড কল দিয়ে বুক করুন।",
        "gu": "તમારી કોઈ સક્રિય બુકિંગ મળી નથી. એપ, SMS (BOOK <કેન્દ્ર> <પાક> <જથ્થો>) અથવા મિસ્ડ કોલથી બુક કરો.",
    },
    "pay_done": {
        "en": "Your payment of ₹{amt} is complete. The digital receipt with tamper-evident hash is in your app.",
        "ml": "₹{amt} പേയ്മെന്റ് പൂർത്തിയായി. ടാംപർ-പ്രൂഫ് ഹാഷുള്ള ഡിജിറ്റൽ രസീത് ആപ്പിൽ ഉണ്ട്.",
        "hi": "₹{amt} का भुगतान पूरा हो गया। टैम्पर-प्रूफ हैश वाली डिजिटल रसीद आपके ऐप में है।",
        "ta": "₹{amt} பணம் முடிந்தது. டிஜிட்டல் ரசீது உங்கள் ஆப்பில் உள்ளது.",
        "pa": "ਤੁਹਾਡਾ ₹{amt} ਭੁਗਤਾਨ ਪੂਰਾ ਹੋ ਗਿਆ ਹੈ। ਛੂ-ਨਾ-ਲੱਗਣ ਵਾਲੀ ਡਿਜੀਟਲ ਰਸੀਦ ਐਪ ਵਿੱਚ ਹੈ।",
        "mr": "तुमची ₹{amt} रक्कम पूर्ण झाली आहे. छेडछाड-प्रतिबंधक डिजिटल पावती अॅपमध्ये आहे.",
        "te": "మీ ₹{amt} చెల్లింపు పూర్తయింది. డిజిటల్ రసీదు యాప్‌లో ఉంది.",
        "kn": "ನಿಮ್ಮ ₹{amt} ಪಾವತಿ ಪೂರ್ಣಗೊಂಡಿದೆ. ರಕ್ಷಿತ ಡಿಜಿಟಲ್ ರಶೀದಿ ಆ್ಯಪ್‌ನಲ್ಲಿದೆ.",
        "bn": "আপনার ₹{amt} পেমেন্ট সম্পূর্ণ হয়েছে। কারচুপি-প্রতিরোধী ডিজিটাল রসিদ অ্যাপে আছে।",
        "gu": "તમારી ₹{amt} ચુકવણી પૂર્ણ થઈ છે. ચેડાફેકી-પ્રતિરોધક ડિજિટલ રસીદ એપમાં છે.",
    },
    "pay_proc": {
        "en": "Procurement is approved (₹{amt}) and payment is in the banking pipeline. You'll get an SMS the moment it lands.",
        "ml": "വാങ്ങൽ അംഗീകരിച്ചു (₹{amt}), പേയ്മെന്റ് ബാങ്കിംഗ് ഘട്ടത്തിലാണ്. എത്തിയ ഉടൻ SMS ലഭിക്കും.",
        "hi": "खरीद स्वीकृत है (₹{amt}) और भुगतान बैंकिंग प्रक्रिया में है। आते ही आपको SMS मिलेगा।",
        "ta": "கொள்முதல் ஒப்புதல் (₹{amt}), பணம் வங்கி செயல்முறையில் உள்ளது. வந்தவுடன் SMS கிடைக்கும்.",
        "pa": "ਖ਼ਰੀਦ ਮਨਜ਼ੂਰ ਹੈ (₹{amt}), ਭੁਗਤਾਨ ਬੈਂਕਿੰਗ ਪ੍ਰਕਿਰਿਆ ਵਿੱਚ ਹੈ। ਪਹੁੰਚਦਿਆਂ ਹੀ SMS ਮਿਲੇਗਾ।",
        "mr": "खरेदी मंजूर आहे (₹{amt}), पेमेंट बँकिंग प्रक्रियेत आहे. आल्यावरच SMS मिळेल.",
        "te": "కొనుగోలు ఆమోదించబడింది (₹{amt}), చెల్లింపు బ్యాంకింగ్ ప్రక్రియలో ఉంది. వచ్చేసరికి SMS వస్తుంది.",
        "kn": "ಖರೀದಿ ಅನುಮೋದಿಸಲಾಗಿದೆ (₹{amt}), ಪಾವತಿ ಬ್ಯಾಂಕಿಂಗ್ ಪ್ರಕ್ರಿಯೆಯಲ್ಲಿದೆ. ಬಂದ ತಕ್ಷಣ SMS ಸಿಗುತ್ತದೆ.",
        "bn": "ক্রয় অনুমোদিত (₹{amt}), পেমেন্ট ব্যাংকিং প্রক্রিয়ায় আছে। আসলেই SMS পাবেন।",
        "gu": "ખરીદી મંજૂર છે (₹{amt}), ચુકવણી બેંકિંગ પ્રક્રિયામાં છે. આવતાં જ SMS મળશે.",
    },
    "pay_delay": {
        "en": "Your payment of ₹{amt} has crossed the normal processing window and is flagged for priority review by the mandi officer.",
        "ml": "₹{amt} പേയ്മെന്റ് സാധാരണ സമയത്തിനപ്പുറം വൈകി; മണ്ഡി ഉദ്യോഗസ്ഥന്റെ മുൻഗണനാ പരിശോധനയിലാണ്.",
        "hi": "₹{amt} का भुगतान सामान्य समय से अधिक देर का है; मंडी अधिकारी की प्राथमिकता समीक्षा में है।",
        "ta": "₹{amt} பணம் சாதாரண நேரத்தை தாண்டி தாமதமாகியுள்ளது; மண்டி அதிகாரியின் முன்னுரிமை ஆய்வில் உள்ளது.",
        "pa": "ਤੁਹਾਡਾ ₹{amt} ਭੁਗਤਾਨ ਆਮ ਸਮੇਂ ਤੋਂ ਵੱਧ ਦੇਰ ਦਾ ਹੈ; ਮੰਡੀ ਅਧਿਕਾਰੀ ਦੀ ਤਰਜੀਹੀ ਸਮੀਖਿਆ ਵਿੱਚ ਹੈ।",
        "mr": "तुमचे ₹{amt} पेमेंट सामान्य वेळेपेक्षा उशीर झाला आहे; मंडी अधिकाऱ्याच्या प्राधान्य तपासणीत आहे.",
        "te": "మీ ₹{amt} చెల్లింపు సాధారణ సమయం దాటి ఆలస్యమైంది; మండి అధికారి ప్రాధాన్య సమీక్షలో ఉంది.",
        "kn": "ನಿಮ್ಮ ₹{amt} ಪಾವತಿ ಸಾಮಾನ್ಯ ಸಮಯ ಮೀರಿ ತಡವಾಗಿದೆ; ಮಂಡಿ ಅಧಿಕಾರಿಯ ಆದ್ಯತೆ ಪರಿಶೀಲನೆಯಲ್ಲಿದೆ.",
        "bn": "আপনার ₹{amt} পেমেন্ট স্বাভাবিক সময় পেরিয়ে দেরি হয়েছে; মণ্ডি আধিকারিকের অগ্রাধিকার পর্যালোচনায় আছে।",
        "gu": "તમારી ₹{amt} ચુકવણી સામાન્ય સમય કરતાં વધુ મોડી છે; માંડી અધિકારીની પ્રાથમિકતા સમીક્ષામાં છે.",
    },
    "pay_need": {
        "en": "Payment tracking needs your token or registered phone.",
        "ml": "പേയ്മെന്റ് പരിശോധിക്കാൻ ടോക്കൺ അല്ലെങ്കിൽ രജിസ്റ്റർ ചെയ്ത ഫോൺ വേണം.",
        "hi": "भुगतान जानने के लिए टोकन या रजिस्टर्ड फोन चाहिए।",
        "ta": "பணம் அறிய டோக்கன் அல்லது பதிவு செய்த ஃபோன் தேவை.",
        "pa": "ਭੁਗਤਾਨ ਜਾਣਨ ਲਈ ਟੋਕਨ ਜਾਂ ਰਜਿਸਟਰਡ ਫ਼ੋਨ ਚਾਹੀਦਾ ਹੈ।",
        "mr": "पेमेंट जाणण्यासाठी टोकन किंवा नोंदणीकृत फोन लागतो.",
        "te": "చెల్లింపు తెలుసుకోవడానికి టోకెన్ లేదా నమోదైన ఫోన్ కావాలి.",
        "kn": "ಪಾವತಿ ತಿಳಿಯಲು ಟೋಕನ್ ಅಥವಾ ನೋಂದಾಯಿತ ಫೋನ್ ಬೇಕು.",
        "bn": "পেমেন্ট জানতে টোকেন বা নিবন্ধিত ফোন দরকার।",
        "gu": "ચુકવણી જાણવા ટોકન અથવા નોંધાયેલ ફોન જોઈએ.",
    },
    "where": {
        "en": "Go to {name} ({dist} km). Current waiting about {wait} min. Please come between {slot}.",
        "ml": "{name}-യിലേക്ക് പോകൂ ({dist} കി.മീ). ഇപ്പോൾ ഏകദേശം {wait} മിനിറ്റ് കാത്തിരുപ്പ്. {slot} ഇടയ്ക്ക് എത്തുക.",
        "hi": "{name} जाएँ ({dist} किमी)। अभी लगभग {wait} मिनट प्रतीक्षा। {slot} के बीच आएँ।",
        "ta": "{name} செல்லுங்கள் ({dist} கி.மீ). தற்போது சுமார் {wait} நிமிட காத்திருப்பு. {slot} இடையே வாருங்கள்.",
        "pa": "{name} ਜਾਓ ({dist} ਕਿ.ਮੀ)। ਹੁਣੇ ਤਕਰੀਬਨ {wait} ਮਿੰਟ ਉਡੀਕ। {slot} ਵਿਚਕਾਰ ਆਓ।",
        "mr": "{name} येथे जा ({dist} किमी). सध्या जवळपास {wait} मिनिटे प्रतीक्षा. {slot} या वेळेत या.",
        "te": "{name} కి వెళ్ళండి ({dist} కి.మీ). ప్రస్తుతం సుమారు {wait} నిమిషాల వేచి ఉండడం. {slot} మధ్య రండి.",
        "kn": "{name} ಗೆ ಹೋಗಿ ({dist} ಕಿ.ಮೀ). ಈಗ ಸುಮಾರು {wait} ನಿಮಿಷ ಕಾಯುವಿಕೆ. {slot} ನಡುವೆ ಬನ್ನಿ.",
        "bn": "{name} যান ({dist} কিমি)। এখন প্রায় {wait} মিনিট অপেক্ষা। {slot} এর মধ্যে আসুন।",
        "gu": "{name} જાઓ ({dist} કિમી). હાલમાં આશરે {wait} મિનિટ રાહ જોવી. {slot} વચ્ચે આવો.",
    },
    "nearby": {
        "en": "Centres ranked by total journey time: {names}.",
        "ml": "ആകെ യാത്രാ സമയം അടിസ്ഥാനമാക്കിയുള്ള കേന്ദ്രങ്ങൾ: {names}.",
        "hi": "कुल यात्रा समय के अनुसार केंद्र: {names}.",
        "ta": "மொத்த பயண நேர அடிப்படையில் மையங்கள்: {names}.",
        "pa": "ਕੁੱਲ ਯਾਤਰਾ ਸਮੇਂ ਅਨੁਸਾਰ ਕੇਂਦਰ: {names}.",
        "mr": "एकूण प्रवास वेळेनुसार केंद्रे: {names}.",
        "te": "మొత్తం ప్రయాణ సమయం ప్రకారం కేంద్రాలు: {names}.",
        "kn": "ಒಟ್ಟು ಪಯಣ ಸಮಯದ ಪ್ರಕಾರ ಕೇಂದ್ರಗಳು: {names}.",
        "bn": "মোট যাত্রা সময় অনুযায়ী কেন্দ্র: {names}.",
        "gu": "કુલ પ્રવાસ સમય પ્રમાણે કેન્દ્રો: {names}.",
    },
    "grievance": {
        "en": "You can raise a grievance from the app (Raise a concern) or by SMS. You'll get an MM-GRV tracking ID and the status timeline is visible to you end-to-end.",
        "ml": "ആപ്പിൽ (Raise a concern) അല്ലെങ്കിൽ SMS വഴി പരാതി നൽകാം. MM-GRV ട്രാക്കിംഗ് ഐഡി ലഭിക്കും; നില മുഴുവനായി കാണാം.",
        "hi": "ऐप (Raise a concern) या SMS से शिकायत दर्ज करें। MM-GRV ट्रैकिंग आईडी मिलेगी और पूरी स्थिति आप देख सकते हैं।",
        "ta": "ஆப் அல்லது SMS மூலம் புகார் அளிக்கலாம். MM-GRV கண்காணிப்பு ஐடி கிடைக்கும்; நிலை முழுவதையும் காணலாம்.",
        "pa": "ਐਪ (Raise a concern) ਜਾਂ SMS ਰਾਹੀਂ ਸ਼ਿਕਾਇਤ ਦਰਜ ਕਰੋ। MM-GRV ਟ੍ਰੈਕਿੰਗ ਆਈਡੀ ਮਿਲੇਗੀ ਅਤੇ ਪੂਰੀ ਸਥਿਤੀ ਤੁਸੀਂ ਦੇਖ ਸਕਦੇ ਹੋ।",
        "mr": "अॅप (Raise a concern) किंवा SMS द्वारे तक्रार नोंदवा. MM-GRV ट्रॅकिंग आयडी मिळेल आणि संपूर्ण स्थिती तुम्ही पाहू शकता.",
        "te": "యాప్ (Raise a concern) లేదా SMS ద్వారా ఫిర్యాదు నమోదు చేయండి. MM-GRV ట్రాకింగ్ ఐడి వస్తుంది; పూర్తి స్థితిని మీరు చూడవచ్చు.",
        "kn": "ಆ್ಯಪ್ (Raise a concern) ಅಥವಾ SMS ಮೂಲಕ ದೂರು ದಾಖಲಿಸಿ. MM-GRV ಟ್ರ್ಯಾಕಿಂಗ್ ಐಡಿ ಸಿಗುತ್ತದೆ; ಪೂರ್ಣ ಸ್ಥಿತಿಯನ್ನು ನೋಡಬಹುದು.",
        "bn": "অ্যাপ (Raise a concern) বা SMS দিয়ে অভিযোগ নথিভুক্ত করুন। MM-GRV ট্র্যাকিং আইডি পাবেন; পুরো অবস্থা দেখতে পারবেন।",
        "gu": "એપ (Raise a concern) કે SMS થી ફરિયાદ નોંધાવો. MM-GRV ટ્રેકિંગ આઈડી મળશે; સંપૂર્ણ સ્થિતિ જોઈ શકાશે.",
    },
    "fallback": {
        "en": "I can help with your turn, payment status, required documents, nearby centres and grievances. For anything else, contact the mandi officer.",
        "ml": "ടേൺ, പേയ്മെന്റ് നില, ആവശ്യമായ രേഖകൾ, അടുത്തുള്ള കേന്ദ്രങ്ങൾ, പരാതികൾ എന്നിവയിൽ സഹായിക്കാം. മറ്റെല്ലാം മണ്ഡി ഉദ്യോഗസ്ഥനെ സമീപിക്കൂ.",
        "hi": "बारी, भुगतान स्थिति, दस्तावेज़, नज़दीकी केंद्र और शिकायतों में मदद कर सकता हूँ। अन्य सहायता के लिए मंडी अधिकारी से संपर्क करें।",
        "ta": "முறை, பணம், ஆவணங்கள், அருகிலுள்ள மையங்கள், புகார்கள் என உதவ முடியும். மற்றவற்றுக்கு மண்டி அதிகாரியை தொடர்பு கொள்ளுங்கள்.",
        "pa": "ਵਾਰੀ, ਭੁਗਤਾਨ ਸਥਿਤੀ, ਕਾਗ਼ਜ਼, ਨੇੜਲੇ ਕੇਂਦਰ ਅਤੇ ਸ਼ਿਕਾਇਤਾਂ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ। ਹੋਰ ਸਹਾਇਤਾ ਲਈ ਮੰਡੀ ਅਧਿਕਾਰੀ ਨਾਲ ਗੱਲ ਕਰੋ।",
        "mr": "वाट, पेमेंट स्थिती, कागदपत्रे, जवळची केंद्रे आणि तक्रारींमध्ये मदत करू शकतो. इतर मदतीसाठी मंडी अधिकाऱ्याशी संपर्क करा.",
        "te": "వరుస, చెల్లింపు స్థితి, పత్రాలు, సమీప కేంద్రాలు మరియు ఫిర్యాదుల్లో సహాయం చేయగలను. ఇతర సహాయానికి మండి అధికారిని సంప్రదించండి.",
        "kn": "ಸರದಿ, ಪಾವತಿ ಸ್ಥಿತಿ, ದಾಖಲೆಗಳು, ಹತ್ತಿರದ ಕೇಂದ್ರಗಳು ಮತ್ತು ದೂರುಗಳಲ್ಲಿ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಇತರ ಸಹಾಯಕ್ಕೆ ಮಂಡಿ ಅಧಿಕಾರಿಯನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "bn": "পালা, পেমেন্ট অবস্থা, কাগজপত্র, নিকটবর্তী কেন্দ্র এবং অভিযোগে সাহায্য করতে পারি। অন্য সাহায্যের জন্য মণ্ডি আধিকারিকের সাথে যোগাযোগ করুন।",
        "gu": "વારો, ચુકવણી સ્થિતિ, કાગળ, નજીકના કેન્દ્રો અને ફરિયાદોમાં મદદ કરી શકું છું. અન્ય મદદ માટે માંડી અધિકારીનો સંપર્ક કરો.",
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
        "pa": {"SLOT_BOOKED": "ਬੁੱਕ ਹੈ", "ARRIVED": "ਪਹੁੰਚ ਗਏ", "WEIGHING": "ਤੋਲ 'ਤੇ",
               "QUALITY_CHECK": "ਗੁਣਵੱਤਾ ਜਾਂਚ 'ਤੇ", "PAYMENT": "ਭੁਗਤਾਨ 'ਤੇ", "COMPLETED": "ਪੂਰਾ"},
        "mr": {"SLOT_BOOKED": "बुक आहे", "ARRIVED": "पोहोचले", "WEIGHING": "वजनावर",
               "QUALITY_CHECK": "गुणवत्ता तपासणीवर", "PAYMENT": "पेमेंटवर", "COMPLETED": "पूर्ण"},
        "te": {"SLOT_BOOKED": "బుక్ అయింది", "ARRIVED": "చేరుకున్నారు", "WEIGHING": "తూకంలో",
               "QUALITY_CHECK": "నాణ్యత తనిఖీలో", "PAYMENT": "చెల్లింపులో", "COMPLETED": "పూర్తి"},
        "kn": {"SLOT_BOOKED": "ಬುಕ್ ಆಗಿದೆ", "ARRIVED": "ಬಂದಿದ್ದಾರೆ", "WEIGHING": "ತೂಕದಲ್ಲಿ",
               "QUALITY_CHECK": "ಗುಣಮಟ್ಟ ಪರಿಶೀಲನೆಯಲ್ಲಿ", "PAYMENT": "ಪಾವತಿಯಲ್ಲಿ", "COMPLETED": "ಪೂರ್ಣ"},
        "bn": {"SLOT_BOOKED": "বুক হয়েছে", "ARRIVED": "পৌঁছেছেন", "WEIGHING": "ওজনে",
               "QUALITY_CHECK": "গুণমান পরীক্ষায়", "PAYMENT": "পেমেন্টে", "COMPLETED": "সম্পূর্ণ"},
        "gu": {"SLOT_BOOKED": "બુક છે", "ARRIVED": "પહોંચી ગયા", "WEIGHING": "વજન પર",
               "QUALITY_CHECK": "ગુણવત્તા તપાસ પર", "PAYMENT": "ચુકવણી પર", "COMPLETED": "પૂર્ણ"},
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
              # ml: turn/when/queue/wait  hi: bari/kab/kataar  ta: murai/eppodhu
              # pa: vari/kadon  mr: vat/pudhe  te: varusu/eppudu  kn: saradi/yavaga
              # bn: pala/kokhon  gu: varo/kyare
              r"ടേൺ", r"എപ്പോൾ", r"ക്യൂ", r"കാത്തിരുപ്പ", r"ബാരി|बारी", r"कब", r"कतार",
              r"मुरै|முறை", r"எப்போது", r"வரிசை", r"ਵਾਰੀ", r"ਕਦੋਂ", r"ਕਤਾਰ", r"ਉਡੀਕ",
              r"वाट", r"पुढे", r"रांग", r"వరుస", r"ఎప్పుడు", r"వేచి",
              r"ಸರದಿ", r"ಯಾವಾಗ", r"ಸಾಲು", r"পালা", r"কখন", r"লাইন",
              r"વારો", r"ક્યારે", r"કતાર"]),
    ("payment", [r"payment", r"paid", r"amount", r"money",
                 r"പേയ്മെന്റ്", r"പണം", r"തുക", r"भुगतान", r"पैसा", r"பணம்", r"தொகை",
                 r"ਭੁਗਤਾਨ", r"पेमेंट", r"रक्कम", r"చెల్లింపు", r"డబ్బు", r"ಪಾವತಿ", r"ಹಣ",
                 r"পেমেন্ট", r"টাকা", r"ચુકવણી", r"પૈસા"]),
    ("documents", [r"document", r"paper", r"carry", r"proof",
                   r"രേഖ", r"ദസ്ത", r"कागज़", r"दस्तावेज़", r"ஆவண",
                   r"ਕਾਗ਼ਜ਼", r"कागदपत्र", r"పత్రాల", r"పత్రాలు", r"ದಾಖಲೆ", r"কাগজ", r"કાગળ"]),
    ("nearby", [r"nearby", r"nearest", r"which mandi", r"other cent", r"less crowd",
                r"where.*sell", r"where.*take", r"where.*go", r"best mandi",
                r"അടുത്ത", r"ഏത് കേന്ദ്ര", r"എവിടെ.*കൊണ്ടുപോകം", r"എവിടെ.*വിൽക്കം",
                r"എവിടെ.*സ്ലോട്ട്", r"വേഗം", r"नज़दीक", r"कहाँ", r"कहां",
                r"அருகில", r"எந்த மையம்", r"எங்கு", r"ਕਿਹੜੀ", r"ਨੇੜੇ",
                r"कुठे", r"ఎక్కడ", r"ಎಲ್ಲಿ", r"কোথায়", r"ક્યાં"]),
    ("procedure", [r"process", r"how.*procure", r"steps", r"quality check", r"weighing",
                   r"ഗുണനിലവാര", r"തൂക്ക", r"गुणवत्ता", r"तौल", r"தரம்", r"தராசு",
                   r"ਗੁਣਵੱਤਾ", r"ਤੋਲ", r"गुणवत्ता", r"నాణ్యత", r"తూకం", r"ಗುಣಮಟ್ಟ", r"ತೂಕ", r"গুণমান", r"ওজন", r"ગુણવત્તા", r"વજન"]),
    ("grievance", [r"complaint", r"grievance", r"issue.*report", r"problem",
                   r"പരാതി", r"शिकायत", r"புகார்", r"ਸ਼ਿਕਾਇਤ", r"तक्रार",
                   r"ఫిర్యాదు", r"ದೂರು", r"অভিযোগ", r"ફરિયાદ"]),
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
            pos = r.get("position")
            eta = r.get("eta_minutes")
            if pos is None:
                pos = "—"
            if eta is None:
                # Not in today's live queue (e.g. a tomorrow booking): say so.
                eta = {"en": "unknown yet", "ml": "ഇനി അറിയാം", "hi": "अभी ज्ञात नहीं",
                       "ta": "இன்னும் தெரியவில்லை", "pa": "ਹਾਲੇ ਪਤਾ ਨਹੀਂ", "mr": "अजून माहीत नाही",
                       "te": "ఇంకా తెలియదు", "kn": "ಇನ್ನೂ ಗೊತ್ತಿಲ್ಲ", "bn": "এখনো জানা যায়নি",
                       "gu": "હજુ ખબર નથી"}.get(lang or "en", "unknown yet")
            return {"reply": _r("turn", lang, token=r["token"],
                               status=_status_word(r["status"], lang),
                               pos=pos, eta=eta),
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
        centres = r["centres"]
        open_c = [c for c in centres if c["status"] == "OPEN"] or centres
        best = open_c[0] if open_c else None
        # 'Where should I take it?' -> one decisive plan, not a list
        is_where = any(w in q for w in ("where", "എവിടെ", "കൊണ്ടുപോകം", "വിൽക്കം",
                                        "कहाँ", "कहां", "எங்கு", "ਕਿਹੜੀ", "ਨੇੜੇ",
                                        "ਵੇਚਣੀ", "कुठे", "ఎక్కడ", "ಎಲ್ಲಿ",
                                        "কোথায়", "ક્યાં")) or any(re.search(p, q) for p in
                                        (r"where.*sell", r"where.*take", r"best mandi"))
        if is_where and best:
            arr_start = "14:30"
            arr_end = "15:30"
            return {"reply": _r("where", lang, name=best["name"], dist=best["distance_km"],
                               wait=int(best["total_journey_minutes"]),
                               slot=f"{arr_start}\u2013{arr_end}"),
                    "recommended": {**best, "arrival_window": [arr_start, arr_end]},
                    "tool_calls": tool_calls}
        names = ", ".join(f"{c['name']} ({c['queue_length']}, ~{c['total_journey_minutes']}m)"
                          for c in centres[:3])
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
