"""The advisor turn: language detection -> bounded tool loop over the provider chain -> guard -> cache.

The model asks questions and narrates; every product decision comes from tools.dispatch (the rules engine).
If every provider fails, the reply is served from the demo cache or generated deterministically by explain()."""
import json
import logging
import os
import re

from openai import APIError, BadRequestError

from ..engine.catalogue import catalogue
from ..llm.providers import AllProvidersFailed, chat_completion
from . import cache
from .explain import explain
from ..engine.bundles import business_type_segments
from ..engine.catalogue import city_tiers
from .language import DONT_KNOW, detect_language, read_facts
from .state import State
from .tools import TOOLS, dispatch, missing_fields, products_named_in

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
TEMPERATURE = 0.3
MAX_TOKENS = 700
HARMONY_LEFTOVER = re.compile(r"<\|[a-z_]+\|>.*?(?=<\|message\|>|$)", re.S)   # stray gpt-oss channel markup, if a provider leaks it
RUPEES = re.compile(r"₹\s?([\d,]+)")

ASK_MISSING = {
    "en": {"business_type": "What does your business do?", "employee_count": "How many people work there, including you?",
           "num_sites": "How many shops or offices do you have, and in which city?", "city": "Which city is the business in?",
           "has_gstin": "Is the business GST registered?",
           "needs": "What would you like to fix or improve: card machine drops, WhatsApp orders, cameras, email, branches, or just reliable internet?"},
    "hi": {"business_type": "आपका बिज़नेस क्या करता है?", "employee_count": "आपके यहाँ कितने लोग काम करते हैं?",
           "num_sites": "आपकी कितनी दुकानें/ऑफिस हैं, और किस शहर में?", "city": "बिज़नेस किस शहर में है?",
           "has_gstin": "क्या बिज़नेस GST में पंजीकृत है?",
           "needs": "आप क्या ठीक करना चाहते हैं: कार्ड मशीन, WhatsApp ऑर्डर, कैमरे, ईमेल, कई ब्रांच, या बस भरोसेमंद इंटरनेट?"},
    "hinglish": {"business_type": "Aapka business kya karta hai?", "employee_count": "Aapke yahan kitne log kaam karte hain?",
                 "num_sites": "Aapki kitni dukaanein/office hain, aur kis sheher mein?", "city": "Business kis sheher mein hai?",
                 "has_gstin": "Kya business GST registered hai?",
                 "needs": "Aap kya theek karna chahte hain: card machine, WhatsApp orders, camere, email, branches, ya bas bharosemand internet?"},
}
OFFLINE_NOTE = {
    "en": "(Our assistant is briefly unavailable, so here is the quote straight from our rules engine.)",
    "hi": "(सहायक अभी कुछ देर के लिए उपलब्ध नहीं है, इसलिए यह कोटेशन सीधे हमारे नियम-इंजन से है।)",
    "hinglish": "(Assistant abhi thodi der ke liye available nahi hai, isliye yeh quote seedha hamare rules engine se hai.)",
}


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = HARMONY_LEFTOVER.sub("", text).replace("<|message|>", "")
    return text.strip()


def _account(st: State, resp) -> None:
    st.usage["calls"] += 1
    u = getattr(resp, "usage", None)
    if u is not None:
        st.usage["prompt_tokens"] += int(getattr(u, "prompt_tokens", 0) or 0)
        st.usage["completion_tokens"] += int(getattr(u, "completion_tokens", 0) or 0)


def ask_next(st: State) -> str:
    """Deterministic question for the first missing fact, in the owner's language."""
    lang = st.language if st.language in ASK_MISSING else "en"
    missing = missing_fields(st.profile, st)
    if not missing:
        st.pending = None
        return explain(st.recommendation, lang) if st.recommendation else ASK_MISSING[lang]["business_type"]
    st.pending = missing[0]
    return ASK_MISSING[lang][missing[0]]


def _guard(text: str, st: State) -> str:
    """Belt and braces after a recommendation: a product named in the text but absent from the engine result gets a
    footnote (the UI renders the card from engine JSON anyway); rupee figures not in the result are logged."""
    if not st.recommendation or not text:
        return text
    cat = catalogue()
    low = text.lower()
    allowed = {cat[i.product_id].name.lower() for i in st.recommendation.items}
    mentioned_excluded = {cat[e.product_id].name.lower() for e in st.recommendation.excluded if e.product_id in cat}
    stray = [p.name for p in cat.values() if p.name.lower() in low and p.name.lower() not in allowed | mentioned_excluded]
    r = st.recommendation
    items = {i.product_id: i.qty for i in r.items}
    ok_numbers = {r.monthly_min, r.monthly_max, r.setup} | st.allowed_numbers
    for pid, q in items.items():
        p = cat[pid]
        ok_numbers |= {p.price_min, p.price_max, p.price_min * q, p.price_max * q, p.setup}
    for pid, q in st.quantities.items():
        if pid in cat:
            ok_numbers |= {cat[pid].price_min * q, cat[pid].price_max * q}
    bad_prices = [m for m in RUPEES.findall(text) if m.replace(",", "").isdigit() and int(m.replace(",", "")) not in ok_numbers
                  and int(m.replace(",", "")) != (st.profile.monthly_spend or -1)]
    if bad_prices:
        st.warnings.append(f"price not in engine result: {bad_prices}")
    if stray:
        st.warnings.append(f"stray product names: {stray}")
        note = {"hi": "\n\n_(ध्यान दें: कोटेशन में केवल कार्ड पर दिखाई गई चीज़ें शामिल हैं।)_",
                "hinglish": "\n\n_(Note: quote mein sirf card par dikhai gayi cheezein shaamil hain.)_"}.get(
            st.language, "\n\n_(Note: only the items on the card are included in your quote.)_")
        return text + note
    return text


def _inject(st: State, name: str, args: dict) -> dict:
    """Run a tool on the server's initiative and record it as if the model had called it, so the model sees the
    result in context and the transcript stays a valid OpenAI tool exchange."""
    st.usage["auto_calls"] = st.usage.get("auto_calls", 0) + 1
    call_id = f"auto_{len(st.messages)}_{name}"
    st.messages.append({"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]})
    result = dispatch(name, args, st)
    st.messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)})
    return result


def _narrate(st: State, max_wait_s: float | None) -> str:
    """One model call with tools disabled: present the result that is already in context."""
    resp, st.provider = chat_completion(messages=st.messages, tools=TOOLS, tool_choice="none",
                                        temperature=TEMPERATURE, max_tokens=MAX_TOKENS, max_wait_s=max_wait_s)
    _account(st, resp)
    text = _clean(resp.choices[0].message.content) or explain(st.recommendation, st.language)
    st.messages.append({"role": "assistant", "content": text})
    return text


def _stalled(st: State) -> bool:
    """True when the model ended its turn with a question although a quote is due: the five facts are known and the
    owner either already said what to solve or has answered one more message since the facts were complete."""
    if st.recommendation is not None or missing_fields(st.profile):
        return False
    return bool(st.profile.needs or st.profile.requested_products or st.needs_known or st.ready_turns >= 1)


def _run(st: State, max_wait_s: float | None) -> str:
    content = _loop(st, max_wait_s)
    if _stalled(st):
        if st.messages and st.messages[-1]["role"] == "assistant" and not st.messages[-1].get("tool_calls"):
            st.messages.pop()                                 # drop the redundant question
        st.needs_known = True
        _inject(st, "get_recommendation", {})
        content = _narrate(st, max_wait_s)
    elif st.recommendation is None and not missing_fields(st.profile):
        st.ready_turns += 1                                   # facts complete; the needs question gets one turn
    return _guard(content, st)


def _complete(st: State, tool_choice: str, max_wait_s: float | None):
    try:
        return chat_completion(messages=st.messages, tools=TOOLS, tool_choice=tool_choice,
                               temperature=TEMPERATURE, max_tokens=MAX_TOKENS, max_wait_s=max_wait_s)
    except BadRequestError:
        if tool_choice == "auto":
            raise
        log.info("advisor: provider rejected tool_choice=%s, using auto", tool_choice)
        return chat_completion(messages=st.messages, tools=TOOLS, tool_choice="auto",
                               temperature=TEMPERATURE, max_tokens=MAX_TOKENS, max_wait_s=max_wait_s)


def _loop(st: State, max_wait_s: float | None) -> str:
    """Bounded tool loop. The first call of each turn must use a tool: gpt-oss otherwise sometimes answered without
    recording the facts it had just been told (observed live), and then re-asked them."""
    content = ""
    for round_no in range(MAX_TOOL_ROUNDS):
        resp, st.provider = _complete(st, "required" if round_no == 0 else "auto", max_wait_s)
        _account(st, resp)
        msg = resp.choices[0].message
        content = _clean(msg.content)
        tool_calls = list(msg.tool_calls or [])
        entry: dict = {"role": "assistant", "content": content or None}
        if tool_calls:
            entry["tool_calls"] = [{"id": tc.id, "type": "function",
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                                   for tc in tool_calls]
        st.messages.append(entry)
        if not tool_calls:
            break
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = dispatch(tc.function.name, args, st)
            st.messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})
    if not content:                                           # model ran out of rounds or returned nothing: never go silent
        content = ask_next(st)
        st.messages.append({"role": "assistant", "content": content})
    return content


YES = re.compile(r"^\W*(?:ok(?:ay)?|yes|yeah|yep|sure|fine|haan|ha|han|ji|theek|thik|go ahead|please|हाँ|हां|ठीक|जी)\b", re.I)
ADD_LINE = re.compile(r"add (?:your|the|a|that) line|add it|include it|line (?:bhi )?(?:add|le|lagao|lagwa)|लाइन (?:भी )?(?:जोड़|लगा)|जोड़ दो|जोड़ दीजिए", re.I)
ANOTHER_SITE = re.compile(r"another (?:branch|shop|store|outlet|office|clinic|location|unit)|one more (?:branch|shop|store|outlet|office|clinic)|"
                          r"also have (?:a |an )?(?:other |second |another )?(?:branch|shop|store|outlet|office|clinic)|second (?:branch|shop|outlet|office)|"
                          r"ek aur (?:dukaan|dukan|branch|shop|office)|एक और (?:दुकान|ब्रांच|शाखा|ऑफिस)|दूसरी (?:दुकान|ब्रांच|शाखा)", re.I)
ASSUMED_WORDS = {
    "en": {"business_type": "a small shop", "employee_count": "1 person", "num_sites": "1 location", "city": "a smaller city", "has_gstin": "no GST"},
    "hi": {"business_type": "छोटी दुकान", "employee_count": "1 व्यक्ति", "num_sites": "1 लोकेशन", "city": "छोटा शहर", "has_gstin": "GST नहीं"},
}


def _offer_line(alt: dict, lang: str) -> str:
    unlocks = ", ".join(alt.get("unlocks") or [])
    adds = ", ".join(alt.get("adds") or [])
    if lang == "hi":
        return (f"{unlocks} केवल Accel की इंटरनेट लाइन पर चलता है। {adds} जोड़ने पर ₹{alt['monthly_from']:,} प्रति माह "
                f"(सेटअप ₹{alt['setup_one_time']:,}) होगा। जोड़ दूँ?")
    return (f"{unlocks} runs only on an Accel internet line. With {adds} added it comes to ₹{alt['monthly_from']:,} per month "
            f"(setup ₹{alt['setup_one_time']:,}). Shall I add it?")


def _offline_reply(st: State, err: Exception) -> str:
    """No LLM reachable: read the facts from the owner's words with rules, ask the next question, or quote from the
    engine. Same gating as online: five facts, then one question about what to solve, then the quote. After two
    "I don't know" answers the quote uses the conservative defaults and says so."""
    log.error("advisor offline: %s", err)
    lang = st.language if st.language in OFFLINE_NOTE else "en"
    st.provider = "offline"
    text = st.user_turns[-1] if st.user_turns else ""
    pending_field = st.pending if st.pending in ASK_MISSING["en"] else None
    facts = read_facts(text, pending_field, city_tiers(), list(business_type_segments()))
    if st.profile.business_type:
        facts.pop("business_type", None)                      # never replace "sari shop" with a generic "shop"
    if "num_sites" not in facts and st.profile.num_sites and ANOTHER_SITE.search(text):
        facts["num_sites"] = st.profile.num_sites + 1
    if st.pending == "accept_line" and (YES.search(text) or ADD_LINE.search(text)):
        facts["accept_accel_line"] = True
    if DONT_KNOW.search(text) and not facts:
        st.unsure_turns += 1
    result: dict = dispatch("update_profile", facts, st) if facts else {}
    if st.recommendation is None:
        if _stalled(st) or st.unsure_turns >= 2:
            st.needs_known = True
            result = dispatch("get_recommendation", {"assume_defaults": st.unsure_turns >= 2}, st)
        elif not missing_fields(st.profile):
            st.ready_turns += 1
    payload = result.get("recommendation") if "recommendation" in result else (result if "bundle" in result else {})
    if st.recommendation:
        parts = [OFFLINE_NOTE[lang], explain(st.recommendation, lang)]
        if st.assumed:
            words = ASSUMED_WORDS["hi" if lang == "hi" else "en"]
            assumed = ", ".join(words[k] for k in st.assumed if k in words)
            parts.append(f"मैंने मान लिया: {assumed}। गलत हो तो बताइए।" if lang == "hi" else f"I assumed {assumed}; tell me if that is wrong.")
        alt = payload.get("alternative_with_accel_line") if payload else None
        if alt:
            parts.append(_offer_line(alt, lang))
            st.pending = "accept_line"
        else:
            st.pending = None
        reply = "\n".join(parts)
    else:
        reply = ask_next(st)
    st.messages.append({"role": "assistant", "content": reply})
    return reply


def step(st: State, user_text: str, *, use_cache: bool = True, max_wait_s: float | None = None) -> str:
    """One owner message in, one advisor reply out. Mutates st (messages, profile, recommendation, usage)."""
    st.set_language(detect_language(user_text, st.language))
    st.user_turns.append(user_text)
    st.messages.append({"role": "user", "content": user_text})
    named = [p for p in products_named_in(user_text) if p not in st.profile.requested_products]
    if named:                                                 # an explicit product ask is never lost to a forgetful model
        _inject(st, "update_profile", {"requested_products": named})

    if os.getenv("ADVISOR_OFFLINE", "").lower() in ("1", "true", "yes"):
        hit = cache.get(st.user_turns, st.language) if use_cache else None
        if hit:
            st.load(hit["state"])
            st.provider = "cache"
            return hit["reply"]
        return _offline_reply(st, RuntimeError("ADVISOR_OFFLINE set"))

    try:
        reply = _run(st, max_wait_s)
    except (AllProvidersFailed, APIError) as e:
        hit = cache.get(st.user_turns, st.language) if use_cache else None
        if hit:
            st.load(hit["state"])
            st.provider = "cache"
            return hit["reply"]
        return _offline_reply(st, e)
    if use_cache:
        try:
            cache.put(st.user_turns, st.language, {"reply": reply, "state": st.to_dict()})
        except OSError as e:                                  # a full disk must not break the conversation
            log.warning("advisor cache write failed: %s", e)
    return reply
