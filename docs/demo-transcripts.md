# Advisor demo transcripts

Recorded live on 2026-11-08 against Groq `openai/gpt-oss-120b` with `scripts/run_llm_scenarios.py`. Advisor replies are
verbatim model output; the engine line under each transcript is the rules-engine result the UI card is rendered from.
Regenerate with `python scripts/run_llm_scenarios.py --save ../docs/demo-transcripts.md` (needs ~40k tokens of quota).

## English: kirana store, no GST, wants WhatsApp Business

**Owner:** I run a kirana store in Lucknow

**Advisor:** How many people work in the store, including yourself?

**Owner:** 2 people including me, just the one shop

**Advisor:** Is your store GST‑registered? If you have a GSTIN, please share it; otherwise just let me know if you're registered or not.

**Owner:** No GST registration

**Advisor:** What problem would you like us to solve? (e.g., faster internet, POS billing, CCTV, WhatsApp orders, cloud email, security, website, etc.)

**Owner:** Customers keep messaging me on WhatsApp for orders. I want a proper WhatsApp business account for the shop.

**Advisor:** Biz 5G AirFiber 100 – fast 100 Mbps wireless broadband, perfect for a shop without fibre.
Business Postpaid 299 – mobile line with 50 GB data and unlimited calls, handy for daily use.
Website + Domain Starter – simple 5‑page site with domain and SSL, helps customers find you online.

From ₹1,497 per month. No setup fee. 12‑month contract. Installation in 2 days.

We left out WhatsApp Business API Starter because it requires an active GST registration, which you don't have. If you need anything else, just let me know.

_Engine result: P04×1, P07×1, P18×1 · from ₹1,497/mo · excluded: P15 (GSTIN_REQUIRED) · 8 LLM calls, ~17.7k tokens_

## Hindi: sari shop, two shops, card machine keeps dropping, wants cameras

**Owner:** मेरी साड़ी की दुकान है दिल्ली में

**Advisor:** आपकी दुकान में कुल कितने लोग काम करते हैं (मालिक सहित)?

**Owner:** पाँच लोग काम करते हैं, दो दुकानें हैं

**Advisor:** क्या आपकी दुकान GST रजिस्टर्ड है? (हाँ या नहीं)

**Owner:** हाँ GST है

**Advisor:** आपको कौन‑सी समस्या हल करनी है? (जैसे POS ड्रॉप, व्हाट्सएप ग्राहक, CCTV, ई‑मेल/डॉक्यूमेंट, डेटा सिक्योरिटी, कई शाखाएँ, मशीन मॉनिटरिंग, वाहन ट्रैकिंग, वेबसाइट, इंटरनेट उपलब्धता, या सिर्फ़ इंटरनेट/मोबाइल चाहिए)(कृपया एक या दो चुनें)

**Owner:** कार्ड मशीन बार-बार बंद हो जाती है और दुकान पर कैमरा भी चाहिए

**Advisor:** Biz Fibre 100 – दो जगहों पर तेज़, अनलिमिटेड फ़ाइबर इंटरनेट।
Business Postpaid 299 – दो मोबाइल लाइन, 50 GB डेटा और अनलिमिटेड कॉल।
Backup 4G/5G Failover – दो साइटों के लिए स्वचालित इंटरनेट बैक‑अप।
Cloud POS & Billing – दो काउंटर के लिए GST‑तैयार बिलिंग, UPI/कार्ड सपोर्ट।
Cloud CCTV – चार कैमरे, क्लाउड में 30 दिन रिकॉर्ड, मोबाइल से देख सकते हैं।

मासिक लागत from ₹5,588 प्रति माह, सेट‑अप ₹7,300 एक बार, 12 महीने का कॉन्ट्रैक्ट, इंस्टॉल 5 दिन में।

कोई प्रोडक्ट बाहर नहीं रखा गया।

क्या आप इस पैकेज को अपनाना चाहेंगे?

_Engine result: P01×2, P07×2, P09×2, P19×2, P23×4 · from ₹5,588/mo · excluded: none · 8 LLM calls, ~18.5k tokens_

## Hinglish: dental clinic, "paanch log", asks for 1 Gbps fibre

**Owner:** Mumbai me meri dental clinic hai

**Advisor:** Dental clinic ke liye aap kitne log kaam karte hain (owner + staff)?

**Owner:** paanch log hain, ek hi clinic hai, GST bhi hai

**Advisor:** Aapka business kya karta hai?
_(Groq was rate-limited on this turn, so this question came from the offline fallback, not the model.)_

**Owner:** Mujhe Biz Fibre 1G chahiye, fast internet

**Advisor:** Biz Fibre 1G – 1 Gbps fast fibre, unlimited data, priority support.
Business Postpaid 599 – 2 mobile lines, 150 GB data each, roaming, priority care.

From ₹5,197 per month, zero setup fee, 12‑month contract, installation in 7 din.

_Engine result: P03×1, P08×2 · from ₹5,197/mo · excluded: none · 5 LLM calls, ~11.7k tokens. "paanch" was recorded as employee_count 5 by the model; P03 is eligible (Mumbai is tier 1, 5 staff, GST)._
