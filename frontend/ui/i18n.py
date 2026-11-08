"""Every UI string in English and Hindi. `t(key)` picks the session language; Hinglish readers get English UI
(the advisor itself answers in Hinglish)."""
import streamlit as st

STRINGS: dict[str, dict[str, str]] = {
    # brand / header
    "brand": {"en": "Accel Business", "hi": "Accel Business"},
    "tagline": {"en": "Internet, mobile and tools for your business, set up in days", "hi": "आपके बिज़नेस के लिए इंटरनेट, मोबाइल और टूल, कुछ ही दिनों में"},
    "partner_banner": {"en": "Brought to you by partner {code}", "hi": "पार्टनर {code} के सहयोग से"},
    "backend_down": {"en": "The service is starting up. Please wait a moment and refresh.", "hi": "सेवा शुरू हो रही है। कृपया थोड़ी देर बाद पेज रीफ़्रेश करें।"},
    "lang_label": {"en": "Language", "hi": "भाषा"},
    # language step
    "welcome": {"en": "Let's find the right internet & tools for your business", "hi": "आपके बिज़नेस के लिए सही इंटरनेट और टूल ढूंढते हैं"},
    "welcome_sub": {"en": "5 minutes. No salesperson. One clear monthly price.", "hi": "5 मिनट। कोई सेल्समैन नहीं। एक साफ़ मासिक कीमत।"},
    "choose_lang": {"en": "Choose your language", "hi": "अपनी भाषा चुनें"},
    # otp
    "otp_title": {"en": "Your mobile number", "hi": "आपका मोबाइल नंबर"},
    "otp_sub": {"en": "We send a one-time code so your quote and order stay linked to you.", "hi": "हम एक बार का कोड भेजते हैं ताकि आपका कोटेशन और ऑर्डर आपसे जुड़ा रहे।"},
    "phone": {"en": "Mobile number", "hi": "मोबाइल नंबर"},
    "send_otp": {"en": "Send code", "hi": "कोड भेजें"},
    "otp_sent": {"en": "Code sent to {phone}. (Demo: the code is 1234.)", "hi": "{phone} पर कोड भेजा गया। (डेमो: कोड 1234 है।)"},
    "otp": {"en": "6-digit code", "hi": "कोड"},
    "verify": {"en": "Verify", "hi": "सत्यापित करें"},
    "bad_phone": {"en": "Please enter a 10-digit mobile number.", "hi": "कृपया 10 अंकों का मोबाइल नंबर डालें।"},
    "bad_otp": {"en": "That code is not right. Try 1234.", "hi": "कोड सही नहीं है। 1234 आज़माएँ।"},
    # chat
    "opening": {"en": "Namaste! I'm your Accel Business advisor. Tell me about your business: what do you do, and in which city?",
                "hi": "नमस्ते! मैं आपका Accel Business सलाहकार हूँ। अपने बिज़नेस के बारे में बताइए: आप क्या करते हैं, और किस शहर में?"},
    "ask_placeholder": {"en": "Tell me about your business…", "hi": "अपने बिज़नेस के बारे में बताइए…"},
    "thinking": {"en": "Thinking…", "hi": "सोच रहा हूँ…"},
    "try_one": {"en": "Or tap an example:", "hi": "या एक उदाहरण चुनें:"},
    "example_1": {"en": "Kirana store in Lucknow, 2 people, one shop, no GST. Customers order on WhatsApp.", "hi": "दिल्ली में साड़ी की दुकान, पाँच लोग, दो दुकानें, GST है। कार्ड मशीन बार-बार बंद होती है और दुकान पर कैमरा भी चाहिए।"},
    "example_2": {"en": "Dental clinic in Mumbai, 5 staff, GST registered, we need fast reliable internet.", "hi": "जयपुर में सैलून, 3 लोग, एक दुकान, GST नहीं। दुकान पर कैमरा चाहिए।"},
    "example_3": {"en": "Restaurant chain, 3 outlets in Bengaluru, 25 staff, no GST yet, cameras and billing must never stop.", "hi": "पुणे में ऑटो-पार्ट्स यूनिट, 12 लोग, GST है। मशीनों की निगरानी और नेटवर्क सुरक्षा चाहिए।"},
    "continue_quote": {"en": "See my price", "hi": "मेरी कीमत देखें"},
    "offline_note": {"en": "Assistant is busy; this reply came straight from our rules engine.", "hi": "सहायक व्यस्त है; यह जवाब सीधे हमारे नियम-इंजन से आया।"},
    # card
    "per_month": {"en": "per month, all included", "hi": "प्रति माह, सब शामिल"},
    "from": {"en": "from", "hi": "शुरू"},
    "your_bundle": {"en": "Your bundle", "hi": "आपका बंडल"},
    "left_out": {"en": "What we left out and why", "hi": "क्या शामिल नहीं किया और क्यों"},
    "added_because": {"en": "Added automatically", "hi": "अपने आप जोड़ा गया"},
    "setup": {"en": "Setup", "hi": "सेटअप"},
    "contract": {"en": "{n}-month contract", "hi": "{n} महीने का अनुबंध"},
    "install": {"en": "Live in ~{n} days", "hi": "~{n} दिन में चालू"},
    "qty_unit": {"en": "× {qty} {unit}", "hi": "× {qty} {unit}"},
    "per_unit_price": {"en": "from ₹{p:,} {unit}", "hi": "₹{p:,} {unit} से"},
    # quote
    "quote_title": {"en": "Your quote", "hi": "आपका कोटेशन"},
    "quote_sub": {"en": "Switch items on or off. Prices update instantly; every change is checked against our rules.", "hi": "चीज़ें चालू/बंद करें। कीमत तुरंत बदलती है; हर बदलाव हमारे नियमों से जाँचा जाता है।"},
    "monthly": {"en": "Monthly", "hi": "मासिक"},
    "vs_today": {"en": "vs ₹{spend:,} you pay today", "hi": "आज के ₹{spend:,} की तुलना में"},
    "not_available": {"en": "Not available for you", "hi": "आपके लिए उपलब्ध नहीं"},
    "add_more": {"en": "Add more", "hi": "और जोड़ें"},
    "needs_fix": {"en": "This combination breaks a rule. Fix it to continue:", "hi": "यह संयोजन नियम तोड़ता है। आगे बढ़ने के लिए ठीक करें:"},
    "continue": {"en": "Continue", "hi": "आगे बढ़ें"},
    "back_chat": {"en": "Back to advisor", "hi": "सलाहकार पर वापस"},
    "quantity": {"en": "Quantity", "hi": "मात्रा"},
    # consent
    "consent_title": {"en": "Before we verify your business", "hi": "व्यवसाय सत्यापन से पहले"},
    "consent_sub": {"en": "We will read four documents. Here is exactly what we use them for.", "hi": "हम चार दस्तावेज़ पढ़ेंगे। हम उनका उपयोग किस लिए करेंगे, यह यहाँ साफ़ लिखा है।"},
    "required": {"en": "required", "hi": "ज़रूरी"},
    "optional": {"en": "optional", "hi": "वैकल्पिक"},
    "agree": {"en": "I agree, verify my business", "hi": "मैं सहमत हूँ, मेरा व्यवसाय सत्यापित करें"},
    "tick_all": {"en": "Tick the required purposes to continue.", "hi": "आगे बढ़ने के लिए ज़रूरी उद्देश्य चुनें।"},
    "notice_full": {"en": "Read the full notice", "hi": "पूरी सूचना पढ़ें"},
    # kyc
    "kyc_title": {"en": "Smart KYC", "hi": "स्मार्ट KYC"},
    "kyc_sub": {"en": "Four photos. We read them and check the GST and Udyam registries in seconds.", "hi": "चार फ़ोटो। हम उन्हें पढ़कर GST और उद्यम रजिस्ट्री सेकंडों में जाँचते हैं।"},
    "kyc_mode_upload": {"en": "Upload my documents", "hi": "मेरे दस्तावेज़ अपलोड करें"},
    "kyc_mode_sample": {"en": "Use a sample applicant", "hi": "नमूना आवेदक चुनें"},
    "sample_pick": {"en": "Sample applicant", "hi": "नमूना आवेदक"},
    "udyam_only": {"en": "I don't have GST (verify with Udyam)", "hi": "मेरे पास GST नहीं है (उद्यम से सत्यापन)"},
    "doc_gst_certificate": {"en": "GST registration certificate", "hi": "GST पंजीकरण प्रमाणपत्र"},
    "doc_udyam_certificate": {"en": "Udyam registration certificate", "hi": "उद्यम पंजीकरण प्रमाणपत्र"},
    "doc_signatory_id": {"en": "Authorised signatory ID", "hi": "अधिकृत हस्ताक्षरकर्ता की पहचान"},
    "doc_address_proof": {"en": "Address proof (electricity bill, last 90 days)", "hi": "पता प्रमाण (बिजली बिल, पिछले 90 दिन)"},
    "verify_docs": {"en": "Verify documents", "hi": "दस्तावेज़ जाँचें"},
    "reading": {"en": "Reading documents and checking registries…", "hi": "दस्तावेज़ पढ़े जा रहे हैं और रजिस्ट्री जाँची जा रही है…"},
    "upload_first": {"en": "Upload at least one document first.", "hi": "पहले कम से कम एक दस्तावेज़ अपलोड करें।"},
    "verdict_PASS": {"en": "Verified", "hi": "सत्यापित"},
    "verdict_REVIEW": {"en": "Needs a better photo", "hi": "बेहतर फ़ोटो चाहिए"},
    "verdict_FAIL": {"en": "Could not verify", "hi": "सत्यापित नहीं हो सका"},
    "checks": {"en": "What we checked", "hi": "हमने क्या जाँचा"},
    "masked_ids": {"en": "Identifiers shown masked", "hi": "पहचान संख्याएँ मास्क करके दिखाई गई हैं"},
    "place_order": {"en": "Place my order", "hi": "ऑर्डर करें"},
    "upload_again": {"en": "Upload again", "hi": "दोबारा अपलोड करें"},
    "talk_human": {"en": "Talk to a human", "hi": "किसी व्यक्ति से बात करें"},
    "handoff_done": {"en": "Done. Our team will call you within one working day.", "hi": "हो गया। हमारी टीम एक कार्यदिवस में आपको कॉल करेगी।"},
    "try_another": {"en": "Try another sample", "hi": "दूसरा नमूना आज़माएँ"},
    "kyc_unavailable": {"en": "The document reader is busy right now. Please try again in a minute.", "hi": "दस्तावेज़ रीडर अभी व्यस्त है। कृपया एक मिनट बाद फिर कोशिश करें।"},
    # tracker
    "tracker_title": {"en": "Your order", "hi": "आपका ऑर्डर"},
    "tracker_sub": {"en": "No status calls needed. Every step and its date is here.", "hi": "स्टेटस के लिए कॉल करने की ज़रूरत नहीं। हर कदम और उसकी तारीख यहाँ है।"},
    "expected": {"en": "expected {date}", "hi": "अनुमानित {date}"},
    "done_on": {"en": "done", "hi": "पूरा"},
    "notify": {"en": "Notify me on WhatsApp / SMS", "hi": "मुझे WhatsApp / SMS पर सूचित करें"},
    "advance_demo": {"en": "Advance stage (demo)", "hi": "अगला चरण (डेमो)"},
    "advanced_toast": {"en": "{label} — {date}", "hi": "{label} — {date}"},
    "withdraw_title": {"en": "Your data", "hi": "आपका डेटा"},
    "withdraw_text": {"en": "You can withdraw consent at any time. We then stop processing and delete what the law does not require us to keep.", "hi": "आप कभी भी सहमति वापस ले सकते हैं। तब हम प्रोसेसिंग रोककर वह सब हटा देते हैं जो कानून को नहीं चाहिए।"},
    "withdraw_btn": {"en": "Withdraw consent", "hi": "सहमति वापस लें"},
    "withdrawn": {"en": "Consent withdrawn and recorded.", "hi": "सहमति वापस ली गई और दर्ज की गई।"},
    "finish": {"en": "Finish", "hi": "समाप्त"},
    # done
    "done_title": {"en": "Thank you!", "hi": "धन्यवाद!"},
    "done_sub": {"en": "Your order is in. Track it any time from the link in your SMS.", "hi": "आपका ऑर्डर दर्ज है। SMS में दिए लिंक से कभी भी ट्रैक करें।"},
    "handoff_title": {"en": "We'll call you", "hi": "हम आपको कॉल करेंगे"},
    "referral": {"en": "Know another business owner? Share your link; you both get one month of a SIM plan free when they activate.",
                 "hi": "किसी और बिज़नेस मालिक को जानते हैं? अपना लिंक साझा करें; उनके चालू होने पर आप दोनों को एक महीने का SIM प्लान मुफ़्त।"},
    "start_again": {"en": "Start again", "hi": "फिर से शुरू करें"},
    # reasons (short Hindi for exclusion codes; English uses the engine sentence)
    "r_TIER_NOT_AVAILABLE": {"en": "only in tier-1 cities", "hi": "केवल बड़े शहरों में उपलब्ध"},
    "r_MIN_EMPLOYEES": {"en": "needs more staff", "hi": "ज़्यादा कर्मचारी चाहिए"},
    "r_MIN_SITES": {"en": "needs more locations", "hi": "ज़्यादा लोकेशन चाहिए"},
    "r_GSTIN_REQUIRED": {"en": "needs GST registration", "hi": "GST पंजीकरण ज़रूरी"},
    "r_GSTIN_NOT_ACTIVE": {"en": "GST is not active", "hi": "GST सक्रिय नहीं है"},
    "r_NEEDS_BASE_LINE": {"en": "needs an Accel internet line", "hi": "Accel की इंटरनेट लाइन ज़रूरी"},
    "r_UNKNOWN_PRODUCT": {"en": "not something we offer", "hi": "हम यह नहीं देते"},
}

UNITS_HI = {"site": "लोकेशन", "line": "लाइन", "ip": "IP", "channel": "चैनल", "number": "नंबर", "pack": "पैक", "account": "अकाउंट",
            "user": "यूज़र", "counter": "काउंटर", "device": "डिवाइस", "camera": "कैमरा", "vehicle": "गाड़ी"}


def lang() -> str:
    return "hi" if st.session_state.get("lang") == "hi" else "en"


def t(key: str, **fmt) -> str:
    s = STRINGS.get(key, {}).get(lang()) or STRINGS.get(key, {}).get("en") or key
    return s.format(**fmt) if fmt else s


def unit_word(unit: str, qty: int = 1) -> str:
    base = (unit or "").lower().replace("per ", "").strip()
    if lang() == "hi":
        return UNITS_HI.get(base, base)
    return base + ("s" if qty > 1 and base and not base.endswith("s") and base.lower() != "ip" else "")


def reason_text(code: str, why: str) -> str:
    return why if lang() == "en" else t(f"r_{code}")
