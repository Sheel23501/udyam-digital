"""Offline tests for the advisor: language helpers, tool dispatch, the tool loop with a fake provider, the guard,
the offline fallback, the cache and the provider chain. No network, no API keys."""
import json
from types import SimpleNamespace

import openai
import pytest

from app.advisor import cache, chat
from app.advisor.explain import explain
from app.advisor.language import detect_language, normalise_city, other_indic_script, parse_bool, parse_count
from app.advisor.state import State
from app.advisor.tools import TOOLS, dispatch
from app.engine.bundles import recommend, validate
from app.engine.catalogue import city_tiers
from app.engine.models import Need, Profile, Reason
from app.llm import providers


# ---------- language helpers ----------
@pytest.mark.parametrize("text,expected", [
    ("मेरी साड़ी की दुकान है", "hi"),
    ("Mumbai me meri dental clinic hai", "hinglish"),
    ("paanch log kaam karte hain", "hinglish"),
    ("I run a kirana store in Lucknow", "en"),
    ("We do not have GST yet", "en"),
])
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_short_replies_keep_current_language():
    assert detect_language("5", "hi") == "hi"
    assert detect_language("ok", "hinglish") == "hinglish"
    assert detect_language("yes we do have GST registration", "hi") == "en"


def test_other_indic_script_detected_as_english_with_notice_path():
    assert other_indic_script("எனக்கு ஒரு கடை உள்ளது")
    assert detect_language("எனக்கு ஒரு கடை உள்ளது") == "en"
    assert not other_indic_script("दुकान")


@pytest.mark.parametrize("value,expected", [
    ("paanch", 5), ("paanch log", 5), ("पाँच", 5), ("दो दुकानें", 2), ("about 10 people", 10), ("just me", 1),
    (7, 7), ("12", 12), ("teen", 3), ("dus", 10), ("a couple of people", 2), ("१५", 15), ("none of that", None),
])
def test_parse_count(value, expected):
    assert parse_count(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("Bombay", "Mumbai"), ("bangalore", "Bengaluru"), ("New Delhi", "Delhi"), ("दिल्ली में", "Delhi"),
    ("Andheri, Mumbai", "Mumbai"), ("noida", "Noida"), ("kochi", "Kochi"), ("", None),
])
def test_normalise_city(value, expected):
    assert normalise_city(value, city_tiers()) == expected


def test_parse_bool_hindi_and_english():
    assert parse_bool("haan") is True and parse_bool("नहीं") is False and parse_bool(True) is True
    assert parse_bool("maybe") is None


# ---------- tool dispatch ----------
def _known(st: State, **over):
    base = dict(business_type="Kirana store", employee_count=3, num_sites=1, city="Lucknow", has_gstin=False)
    base.update(over)
    return dispatch("update_profile", base, st)


def test_tool_schemas_are_openai_function_format():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"update_profile", "get_recommendation"}
    assert all(t["type"] == "function" for t in TOOLS)
    assert set(Need.__members__.values()) >= set(Need(n) for n in TOOLS[0]["function"]["parameters"]["properties"]["needs"]["items"]["enum"])


def test_update_profile_normalises_and_reports_missing():
    st = State()
    r = dispatch("update_profile", {"business_type": " salon ", "employee_count": "teen", "city": "Bombay"}, st)
    assert st.profile.employee_count == 3 and st.profile.city == "Mumbai" and st.profile.business_type == "salon"
    assert r["still_needed"] == ["num_sites", "has_gstin", "needs"]


def test_quote_waits_until_the_owner_has_been_asked_what_to_solve():
    st = State()
    dispatch("update_profile", dict(business_type="Kirana store", employee_count=3, num_sites=1, city="Lucknow", has_gstin=False), st)
    r = dispatch("get_recommendation", {}, st)
    assert r["error"] == "missing_fields" and r["missing"] == ["needs"] and "no_specific_need" in r["hint"]
    r = dispatch("update_profile", {"no_specific_need": True}, st)
    assert r["note"].startswith("all facts known")
    assert "bundle" in dispatch("get_recommendation", {}, st)
    st2 = State()
    dispatch("update_profile", dict(business_type="Law office", employee_count=6, num_sites=1, city="Mumbai", has_gstin=True,
                                    requested_products=["P03"]), st2)
    assert "bundle" in dispatch("get_recommendation", {}, st2)      # an explicit product ask counts as the need


def test_language_change_rewrites_the_system_prompt():
    st = State()
    assert "Write your reply in English" in st.messages[0]["content"]
    st.set_language("hi")
    assert "Hindi (Devanagari script)" in st.messages[0]["content"] and st.profile.language == "hi"
    assert len([m for m in st.messages if m["role"] == "system"]) == 1


def test_get_recommendation_refuses_until_facts_known_then_works():
    st = State()
    r = dispatch("get_recommendation", {}, st)
    assert r["error"] == "missing_fields" and "has_gstin" in r["missing"]
    _known(st, needs=["whatsapp_customers"])
    r = dispatch("get_recommendation", {}, st)
    ids = {b["id"] for b in r["bundle"]}
    assert "P18" in ids and "P07" in ids and ids & {"P01", "P04"}
    assert {(e["id"], e["reason"]) for e in r["excluded"]} == {("P15", "GSTIN_REQUIRED")}
    assert r["monthly_from"] == st.recommendation.monthly_min > 0
    assert all("price_from_per_unit" in b for b in r["bundle"])


def test_assume_defaults_is_conservative_and_recorded():
    st = State()
    r = dispatch("get_recommendation", {"assume_defaults": True}, st)
    assert r["assumed"] == {"business_type": "small business", "employee_count": 1, "num_sites": 1, "city": None, "has_gstin": False}
    ids = {b["id"] for b in r["bundle"]}
    assert ids & {"P01", "P04"} and not ids & {"P03", "P05", "P06", "P21"}
    assert not validate({b["id"]: b["qty"] for b in r["bundle"]}, st.profile).violations
    dispatch("update_profile", {"employee_count": 12}, st)
    assert "employee_count" not in st.assumed


def test_profile_change_after_quote_recomputes_without_stale_items():
    st = State()
    _known(st, business_type="Law office", employee_count=6, city="Mumbai", has_gstin=True, requested_products=["P03"])
    r = dispatch("get_recommendation", {}, st)
    assert "P03" in {b["id"] for b in r["bundle"]}
    r = dispatch("update_profile", {"city": "Nashik"}, st)
    assert "recommendation" in r and "do not call get_recommendation again" in r["note"]
    ids = {b["id"] for b in r["recommendation"]["bundle"]}
    assert "P03" not in ids and "P02" in ids
    assert {(e["id"], e["reason"]) for e in r["recommendation"]["excluded"]} == {("P03", "TIER_NOT_AVAILABLE")}


def test_second_branch_doubles_per_site_items():
    st = State()
    _known(st, business_type="Pharmacy", city="Noida", has_gstin=True, needs=["cctv"])
    dispatch("get_recommendation", {}, st)
    r = dispatch("update_profile", {"num_sites": 2}, st)
    qty = {b["id"]: b["qty"] for b in r["recommendation"]["bundle"]}
    assert qty["P23"] == 4 and qty["P01"] == 2


def test_gstin_is_looked_up_in_the_registry():
    st = State()
    r = _known(st, business_type="Coaching centre", employee_count=6, city="Kochi", gstin="32hjjxe5083y1zr",
               requested_products=["Toll-free Number", "P15", "Starlink"])
    assert r["gstin_registry"]["found"] and r["gstin_registry"]["status"] == "Cancelled"
    assert st.profile.has_gstin is True and st.profile.gstin == "32HJJXE5083Y1ZR"
    assert st.profile.requested_products == ["P13", "P15", "Starlink"]
    r = dispatch("get_recommendation", {}, st)
    exc = {e["id"]: e["reason"] for e in r["excluded"]}
    assert exc == {"P13": "GSTIN_NOT_ACTIVE", "P15": "GSTIN_NOT_ACTIVE", "Starlink": "UNKNOWN_PRODUCT"}
    assert "P18" in {b["id"] for b in r["bundle"]}          # GST-free fallback for WhatsApp


def test_unknown_gstin_is_kept_for_kyc_but_not_trusted():
    st = State()
    r = _known(st, has_gstin=True, gstin="27AAAAA0000A1Z5")
    assert r["gstin_registry"] == {"found": False, "note": "not in the GST registry; it will be verified at KYC"}
    assert st.profile.gstin_status is None


def test_services_only_offers_a_line_and_accept_adds_it():
    st = State()
    _known(st, business_type="Salon", city="Jaipur", needs=["services_only", "cctv"])
    r = dispatch("get_recommendation", {}, st)
    assert r["bundle"] == [] and r["excluded"][0]["reason"] == "NEEDS_BASE_LINE"
    alt = r["alternative_with_accel_line"]
    assert alt["unlocks"] == ["Cloud CCTV"] and alt["adds"] and alt["monthly_from"] > 0
    r = dispatch("update_profile", {"accept_accel_line": True}, st)
    ids = {b["id"] for b in r["recommendation"]["bundle"]}
    assert "P23" in ids and ids & {"P01", "P02", "P04"} and not ids & {"P07", "P08"}
    assert "alternative_with_accel_line" not in r["recommendation"]


def test_services_only_without_line_dependents_adds_no_line():
    st = State()
    _known(st, business_type="CA firm", employee_count=6, city="Pune", has_gstin=True, needs=["services_only", "email_docs", "data_security"])
    r = dispatch("get_recommendation", {}, st)
    ids = {b["id"] for b in r["bundle"]}
    assert {"P16", "P17", "P20"} <= ids and not ids & {"P01", "P02", "P03", "P04", "P05", "P06"}
    assert {e["id"] for e in r["excluded"]} == {"P21"}        # firewall needs an Accel line


def test_quantity_override_changes_price_only_for_items_in_bundle():
    st = State()
    _known(st, needs=["cctv"])
    dispatch("get_recommendation", {}, st)
    r = dispatch("update_profile", {"quantities": {"P23": 50, "P21": 3}}, st)
    rec = r["recommendation"]
    assert rec["quantities_overridden"] == {"P23": 50}
    assert rec["monthly_from"] == st.recommendation.monthly_min - 2 * 199 + 50 * 199


def test_recommend_line_for_addons_flag_is_backwards_compatible():
    prof = Profile(business_type="Salon", employee_count=3, num_sites=1, city="Jaipur", has_gstin=False,
                   needs=[Need.SERVICES_ONLY, Need.CCTV])
    plain = recommend(prof)
    assert [e.reason for e in plain.excluded] == [Reason.NEEDS_BASE_LINE] and not plain.items
    with_line = recommend(prof, line_for_addons=True)
    ids = {i.product_id for i in with_line.items}
    assert "P23" in ids and ids & {"P01", "P02", "P04"} and not validate({i.product_id: i.qty for i in with_line.items}, prof).violations


def test_unknown_tool():
    assert dispatch("nope", {}, State())["error"].startswith("unknown tool")


# ---------- explain ----------
def test_explain_english_and_hindi_mention_items_price_and_reasons():
    prof = Profile(business_type="Tailoring shop", employee_count=6, num_sites=1, city="Delhi", has_gstin=True,
                   needs=[Need.DATA_SECURITY if hasattr(Need, "DATA_SECURITY") else Need.SECURITY], requested_products=["P21"])
    b = recommend(prof)
    en, hi = explain(b, "en"), explain(b, "hi")
    assert f"₹{b.monthly_min:,}" in en and f"₹{b.monthly_min:,}" in hi
    assert "Endpoint Security" in en and "Endpoint Security" in hi
    assert "Managed Firewall needs at least 10 staff" in en
    assert "कम से कम 10 कर्मचारी" in hi


def test_explain_every_reason_has_a_sentence_in_both_languages():
    from app.advisor.explain import reason_sentence
    from app.engine.models import Exclusion
    for reason in Reason:
        ex = Exclusion(product_id="P21" if reason != Reason.UNKNOWN_PRODUCT else "PX", reason=reason, detail="d")
        assert reason_sentence(ex, "en") and reason_sentence(ex, "hi")


# ---------- the tool loop with a fake provider ----------
def _msg(content=None, tool_calls=None):
    tcs = [SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a))) for i, (n, a) in enumerate(tool_calls or [])]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tcs or None))],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


class FakeLLM:
    """Scripted provider: each call pops the next canned response and records the messages it was sent."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.seen = []

    def __call__(self, max_wait_s=None, **kwargs):
        self.seen.append(list(kwargs["messages"]))
        if not self.responses:
            raise providers.AllProvidersFailed("script exhausted")
        return self.responses.pop(0), "fake"


def test_step_runs_tools_then_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([
        _msg(tool_calls=[("update_profile", {"business_type": "Kirana store", "employee_count": 2, "num_sites": 1, "city": "Lucknow",
                                              "has_gstin": False, "needs": ["whatsapp_customers"]}),
                         ("get_recommendation", {})]),
        _msg(content="Here is your plan: Website + Domain Starter and a Business Postpaid 299 line, from ₹1,497 per month."),
    ])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    reply = step = chat.step(st, "I run a kirana store in Lucknow, 2 people, one shop, no GST, customers message on WhatsApp")
    assert reply.startswith("Here is your plan")
    assert st.recommendation is not None and st.provider == "fake" and st.usage["calls"] == 2
    roles = [m["role"] for m in st.messages]
    # system, user, [server: certain facts from the message -> assistant+tool], model: 2 tool calls -> 2 tool results, reply
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "tool", "assistant"]
    assert st.messages[2]["tool_calls"][0]["id"].startswith("auto_")
    tool_payloads = [json.loads(m["content"]) for m in st.messages if m["role"] == "tool"]
    assert tool_payloads[0]["ok"] and tool_payloads[1]["ok"] and "bundle" in tool_payloads[2]
    assert st.messages[4]["tool_calls"][0]["function"]["name"] == "update_profile"
    assert cache.get(st.user_turns, st.language)["reply"] == reply       # cached for the demo fallback


def test_guard_flags_products_not_in_engine_result(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([
        _msg(tool_calls=[("update_profile", {"business_type": "Kirana store", "employee_count": 2, "num_sites": 1, "city": "Lucknow",
                                              "has_gstin": False, "no_specific_need": True}),
                         ("get_recommendation", {})]),
        _msg(content="I recommend Managed Firewall and Internet Leased Line 100 for ₹99 per month."),
    ])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    reply = chat.step(st, "kirana store Lucknow 2 people one shop no gst", use_cache=False)
    assert "only the items on the card" in reply
    assert any("stray product names" in w for w in st.warnings) and any("price not in engine result" in w for w in st.warnings)


def test_guard_does_not_flag_excluded_items_or_engine_prices():
    st = State()
    _known(st, business_type="Tailoring shop", employee_count=6, city="Delhi", has_gstin=True, requested_products=["P21"], needs=["data_security"])
    dispatch("get_recommendation", {}, st)
    r = st.recommendation
    text = f"Endpoint Security and Cloud Backup 1 TB from ₹{r.monthly_min:,} per month. Managed Firewall needs at least 10 staff, so I left it out."
    assert chat._guard(text, st) == text and not st.warnings


def test_loop_is_bounded_and_never_silent(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([_msg(tool_calls=[("get_recommendation", {})]) for _ in range(chat.MAX_TOOL_ROUNDS + 2)])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    reply = chat.step(st, "hello", use_cache=False)
    assert st.usage["calls"] == chat.MAX_TOOL_ROUNDS
    assert reply == "What does your business do?"            # deterministic question for the first missing fact


def test_offline_fallback_uses_engine_explanation(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    st = State()
    _known(st, needs=["cctv"])
    dispatch("get_recommendation", {}, st)
    monkeypatch.setattr(chat, "chat_completion", FakeLLM([]))
    reply = chat.step(st, "ok what do you suggest", use_cache=False)
    assert st.provider == "offline" and "briefly unavailable" in reply and "Cloud CCTV" in reply
    assert st.messages[-1]["role"] == "assistant"


def test_offline_fallback_in_hindi_asks_the_next_question(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    monkeypatch.setattr(chat, "chat_completion", FakeLLM([]))
    st = State()
    reply = chat.step(st, "नमस्ते", use_cache=False)
    assert st.language == "hi" and reply == "आपका बिज़नेस क्या करता है?"
    assert "Hindi (Devanagari script)" in st.messages[0]["content"]
    reply = chat.step(st, "मेरी दुकान है", use_cache=False)
    assert st.profile.business_type == "shop" and reply == "आपके यहाँ कितने लोग काम करते हैं?"


def test_whole_hindi_conversation_works_offline(monkeypatch, tmp_path):
    """The demo conversation must reach a valid quote with no network at all."""
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    st = State()
    for turn in ["मेरी साड़ी की दुकान है दिल्ली में", "पाँच लोग काम करते हैं, दो दुकानें हैं", "हाँ GST है",
                 "कार्ड मशीन बार-बार बंद हो जाती है और दुकान पर कैमरा भी चाहिए"]:
        reply = chat.step(st, turn, use_cache=False)
    assert st.provider == "offline" and st.recommendation is not None
    ids = {i.product_id for i in st.recommendation.items}
    assert {"P09", "P19", "P23"} <= ids and ids & {"P01", "P02", "P03"}
    assert "₹" in reply and "प्रति माह" in reply
    assert not validate({i.product_id: i.qty for i in st.recommendation.items}, st.profile).violations


def test_offline_bare_answers_fill_the_field_just_asked(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    st = State()
    replies = [chat.step(st, t, use_cache=False) for t in
               ["I run a kirana store in Lucknow", "2", "1", "no", "just internet"]]
    assert replies[0] == "How many people work there, including you?"
    assert st.profile.employee_count == 2 and st.profile.num_sites == 1 and st.profile.has_gstin is False
    assert st.recommendation is not None and "From ₹" in replies[-1]


@pytest.mark.parametrize("text,pending,expected", [
    ("Coaching centre in Kolkata, 12 teachers, one centre, GST registered", None,
     {"employee_count": 12, "num_sites": 1, "city": "Kolkata", "has_gstin": True, "business_type": "coaching centre"}),
    ("paanch log hain, ek hi clinic hai, GST bhi hai", None, {"employee_count": 5, "num_sites": 1, "has_gstin": True, "business_type": "clinic"}),
    ("We don't have GST yet, applying next month", None, {"has_gstin": False}),
    ("haan", "has_gstin", {"has_gstin": True}),
    ("Just reliable internet for the classrooms", "needs", {"no_specific_need": True}),
])
def test_read_facts(text, pending, expected):
    from app.advisor.language import read_facts
    from app.engine.bundles import business_type_segments
    assert read_facts(text, pending, city_tiers(), list(business_type_segments())) == expected


def test_cache_serves_exact_transcript_when_provider_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    good = FakeLLM([_msg(content="Namaste! What does your business do?")])
    monkeypatch.setattr(chat, "chat_completion", good)
    st1 = State()
    first = chat.step(st1, "Hi there, I need internet for my shop")
    monkeypatch.setattr(chat, "chat_completion", FakeLLM([]))
    st2 = State()
    again = chat.step(st2, "hi there,  I need internet for my shop ")     # whitespace/case-insensitive key
    assert again == first and st2.provider == "cache" and st2.user_turns == st1.user_turns


def test_offline_env_flag_never_calls_a_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    called = FakeLLM([_msg(content="should not be used")])
    monkeypatch.setattr(chat, "chat_completion", called)
    st = State()
    reply = chat.step(st, "I have a shop")
    assert not called.seen and st.provider == "offline" and reply


def test_state_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    st = State()
    _known(st, needs=["cctv"])
    dispatch("get_recommendation", {}, st)
    st.messages.append({"role": "user", "content": "x"})
    d = json.loads(json.dumps(st.to_dict(), ensure_ascii=False))
    st2 = State.from_dict(d)
    assert st2.profile == st.profile and st2.recommendation == st.recommendation
    assert st2.messages[0]["role"] == "system" and st2.messages[1:] == st.messages[1:]


# ---------- provider chain ----------
def test_chain_respects_order_and_skips_missing_keys(monkeypatch):
    monkeypatch.setenv("ADVISOR_PROVIDER_CHAIN", "cerebras,groq,gemini")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ADVISOR_MODEL_GROQ", "openai/gpt-oss-120b")
    monkeypatch.delenv("ADVISOR_REASONING_EFFORT", raising=False)
    names = [p.name for p in providers.chain()]
    assert names == ["groq", "gemini"]
    groq = providers.chain()[0]
    assert groq.extra == {"reasoning_effort": "medium"} and providers.chain()[1].extra == {}


def test_chain_without_keys_is_empty_and_fails_clearly(monkeypatch):
    for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert providers.chain() == []
    with pytest.raises(providers.AllProvidersFailed):
        providers.chat_completion(messages=[])


def _status_error(cls, status):
    resp = SimpleNamespace(status_code=status, headers={}, request=None)
    err = cls.__new__(cls)
    err.status_code = status
    err.response = resp
    err.message = f"http {status}"
    err.body = None
    return err


def test_chat_completion_falls_through_on_429_and_5xx_but_raises_400(monkeypatch):
    monkeypatch.setenv("ADVISOR_MAX_WAIT_S", "0")
    calls = []

    def fake_chain():
        return [providers.Provider("a", "u", "k", "m"), providers.Provider("b", "u", "k", "m"), providers.Provider("c", "u", "k", "m")]

    def fake_call(p, kwargs):
        calls.append(p.name)
        if p.name == "a":
            raise _status_error(openai.RateLimitError, 429)
        if p.name == "b":
            raise _status_error(openai.InternalServerError, 503)
        return "ok"

    monkeypatch.setattr(providers, "chain", fake_chain)
    monkeypatch.setattr(providers, "_call", fake_call)
    assert providers.chat_completion(messages=[]) == ("ok", "c") and calls == ["a", "b", "c"]

    def bad_request(p, kwargs):
        raise _status_error(openai.BadRequestError, 400)
    monkeypatch.setattr(providers, "_call", bad_request)
    with pytest.raises(openai.BadRequestError):
        providers.chat_completion(messages=[])


def test_chat_completion_gives_up_when_everyone_is_rate_limited(monkeypatch):
    monkeypatch.setenv("ADVISOR_MAX_WAIT_S", "0")
    monkeypatch.setattr(providers, "chain", lambda: [providers.Provider("a", "u", "k", "m")])
    monkeypatch.setattr(providers, "_call", lambda p, kw: (_ for _ in ()).throw(_status_error(openai.RateLimitError, 429)))
    with pytest.raises(providers.AllProvidersFailed):
        providers.chat_completion(messages=[])


# ---------- product names in the owner's own words ----------
@pytest.mark.parametrize("text,expected", [
    ("Mujhe Biz Fibre 1G chahiye, fast internet", ["P03"]),
    ("We want the 1 Gbps Biz Fibre plan.", ["P03"]),
    ("I want a managed firewall to keep our computers safe", ["P21"]),
    ("We want a toll-free number and the WhatsApp Business API.", ["P13", "P15"]),
    ("I want the 5G AirFiber because fibre takes too long", ["P04"]),
    ("Customers keep messaging me on WhatsApp for orders", []),        # a need, not a product ask
    ("I don't want a firewall, just internet", []),
    ("firewall nahi chahiye", ["P21"]),                                 # Hindi negation comes after: model handles it
    ("Do you have Starlink?", []),
])
def test_products_named_in(text, expected):
    from app.advisor.tools import products_named_in
    assert products_named_in(text) == expected


def test_named_product_is_injected_before_the_model_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([_msg(content="Which city is the clinic in?")])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    chat.step(st, "We want the 1 Gbps Biz Fibre plan", use_cache=False)
    assert st.profile.requested_products == ["P03"] and st.usage["auto_calls"] == 1
    sent = fake.seen[0]
    assert sent[-2]["tool_calls"][0]["id"].startswith("auto_") and sent[-1]["role"] == "tool"


def test_named_product_after_quote_recomputes(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    st = State()
    _known(st, business_type="Tailoring shop", employee_count=6, city="Delhi", has_gstin=True, no_specific_need=True)
    dispatch("get_recommendation", {}, st)
    monkeypatch.setattr(chat, "chat_completion", FakeLLM([_msg(content="Managed Firewall needs at least 10 staff, so I left it out.")]))
    chat.step(st, "Can I also get a managed firewall?", use_cache=False)
    assert {e.product_id: e.reason for e in st.recommendation.excluded} == {"P21": Reason.MIN_EMPLOYEES}


# ---------- auto-quote when the model stalls ----------
FACTS = {"business_type": "Physiotherapy clinic", "employee_count": 8, "num_sites": 1, "city": "Nagpur", "has_gstin": True}


def test_stall_with_need_known_is_quoted_in_the_same_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([
        _msg(tool_calls=[("update_profile", {**FACTS, "needs": ["uptime"]})]),
        _msg(content="Anything else you need?"),                              # stall
        _msg(content="Biz Fibre 300 with a backup line, from ₹2,000 per month."),  # narration
    ])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    reply = chat.step(st, "Physio clinic in Nagpur, 8 staff, one clinic, GST, internet must never go down", use_cache=False)
    assert st.recommendation is not None and reply.startswith("Biz Fibre 300")
    assert not any(m.get("content") == "Anything else you need?" for m in st.messages)   # stalled question dropped
    injected = [tc["function"]["name"] for m in st.messages for tc in (m.get("tool_calls") or []) if tc["id"].startswith("auto_")]
    assert injected == ["update_profile", "get_recommendation"]       # certain facts first, then the forced quote


def test_needs_question_gets_exactly_one_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([
        _msg(tool_calls=[("update_profile", FACTS)]),
        _msg(content="What would you like to improve?"),
        _msg(content="Got it. Anything else?"),                               # owner answered; model stalls again
        _msg(content="Here is your plan, from ₹1,000 per month."),
    ])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    first = chat.step(st, "Physio clinic in Nagpur, 8 staff, one clinic, GST registered", use_cache=False)
    assert first == "What would you like to improve?" and st.recommendation is None and st.ready_turns == 1
    second = chat.step(st, "Online appointments mostly", use_cache=False)
    assert st.recommendation is not None and second.startswith("Here is your plan")


def test_no_auto_quote_while_facts_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    fake = FakeLLM([_msg(content="How many people work there?")])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    chat.step(st, "I run a salon", use_cache=False)
    injected = [tc["function"]["name"] for m in st.messages for tc in (m.get("tool_calls") or []) if tc["id"].startswith("auto_")]
    assert st.recommendation is None and st.ready_turns == 0 and "get_recommendation" not in injected


def test_alternative_prices_are_whitelisted_for_the_guard():
    st = State()
    _known(st, business_type="Salon", city="Jaipur", needs=["services_only", "cctv"])
    r = dispatch("get_recommendation", {}, st)
    alt = r["alternative_with_accel_line"]
    text = f"With our line it is from ₹{alt['monthly_from']:,} per month, setup ₹{alt['setup_one_time']:,}."
    assert chat._guard(text, st) == text and not st.warnings
    chat._guard("Only ₹1,497 per month!", st)
    assert st.warnings == ["price not in engine result: ['1,497']"]


def test_first_call_of_a_turn_requires_a_tool_and_falls_back_if_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    choices = []

    def fake(max_wait_s=None, **kw):
        choices.append(kw["tool_choice"])
        if kw["tool_choice"] == "required":
            raise _status_error(openai.BadRequestError, 400)
        return _msg(content="What does your business do?"), "fake"

    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    assert chat.step(st, "hello", use_cache=False) == "What does your business do?"
    assert choices == ["required", "auto"]


def test_default_chain_includes_card_free_backups_in_order(monkeypatch):
    for k in ("ADVISOR_PROVIDER_CHAIN", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k in ("GROQ_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "x")
    chain = providers.chain()
    assert [p.name for p in chain] == ["groq", "mistral", "openrouter", "gemini"]       # cerebras skipped: no key
    by = {p.name: p for p in chain}
    assert by["mistral"].base_url == "https://api.mistral.ai/v1" and by["mistral"].model == "mistral-small-latest"
    assert by["mistral"].extra == {}                                                     # reasoning_effort is gpt-oss only
    assert by["openrouter"].model == "openai/gpt-oss-120b:free" and by["openrouter"].extra == {"reasoning_effort": "medium"}


def test_all_transcript_scenarios_pass_with_no_llm(monkeypatch, tmp_path):
    """Every shipped transcript scenario must reach a rule-valid quote through the offline path alone, so a
    rate-limited or unreachable provider during the demo degrades the prose, never the recommendation."""
    import sys
    from pathlib import Path
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_llm_scenarios as runner
    scenarios = runner.load([str(Path(__file__).resolve().parent / "llm_scenarios")])
    assert len(scenarios) >= 16
    failures = {}
    for sc in scenarios:
        st = State()
        for turn in sc["turns"]:
            chat.step(st, turn, use_cache=False)
        problems = runner.check(sc, st)
        if problems:
            failures[sc["name"]] = problems
    assert not failures, failures


def test_explain_empty_bundle_has_no_zero_price():
    prof = Profile(business_type="Salon", employee_count=3, num_sites=1, city="Jaipur", has_gstin=False,
                   needs=[Need.SERVICES_ONLY, Need.CCTV])
    text = explain(recommend(prof), "en")
    assert "₹0" not in text and "Cloud CCTV runs only on an Accel internet line" in text
    assert "₹0" not in explain(recommend(prof), "hi")


def test_explain_pluralises_english_units():
    prof = Profile(business_type="Pharmacy", employee_count=3, num_sites=2, city="Noida", has_gstin=True, needs=[Need.CCTV])
    text = explain(recommend(prof), "en")
    assert "× 4 cameras" in text and "× 2 sites" in text and "× 2 lines" in text


def test_generic_shop_is_micro_not_a_workshop():
    from app.engine.bundles import infer_segment
    assert infer_segment(Profile(business_type="shop", employee_count=1)) == "micro"
    assert infer_segment(Profile(business_type="small shop", employee_count=1)) == "micro"
    assert infer_segment(Profile(business_type="furniture workshop", employee_count=12)) == "mfg"
    assert infer_segment(Profile(business_type="clinic", employee_count=4)) == "prof"


def test_adapt_messages_handles_gemini_thought_signatures():
    hist = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "update_profile", "arguments": "{}"},
                 "extra_content": {"google": {"thought_signature": "REAL"}}},
                {"id": "auto_1", "type": "function", "function": {"name": "get_recommendation", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "a", "content": "{}"}]
    g = providers.adapt_messages("gemini", hist)
    sigs = [tc["extra_content"]["google"]["thought_signature"] for tc in g[1]["tool_calls"]]
    assert sigs == ["REAL", providers.GEMINI_SKIP_SIGNATURE]          # real one kept, injected one gets the placeholder
    other = providers.adapt_messages("groq", hist)
    assert all("extra_content" not in tc for tc in other[1]["tool_calls"])
    assert "extra_content" in hist[1]["tool_calls"][0] and "extra_content" not in hist[1]["tool_calls"][1]   # stored history untouched


def test_loop_keeps_the_signature_the_model_returned(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "ADVISOR_CACHE", tmp_path)
    tc = SimpleNamespace(id="c0", function=SimpleNamespace(name="update_profile", arguments="{}"),
                         model_extra={"extra_content": {"google": {"thought_signature": "SIG"}}})
    first = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))], usage=None)
    fake = FakeLLM([first, _msg(content="Which city?")])
    monkeypatch.setattr(chat, "chat_completion", fake)
    st = State()
    chat.step(st, "I run a shop", use_cache=False)
    stored = next(m for m in st.messages if m.get("tool_calls") and m["tool_calls"][0]["id"] == "c0")
    assert stored["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "SIG"}}


# ---------- certain-facts safety net (online mode) ----------
@pytest.mark.parametrize("text,expected", [
    ("We are a physiotherapy clinic in Nagpur with 8 staff, one clinic, GST registered.",
     {"employee_count": 8, "num_sites": 1, "city": "Nagpur", "has_gstin": True}),
    ("I want a managed firewall to keep our computers safe", {"requested_products": ["P21"], "needs": ["data_security"]}),
    ("I want the 5G AirFiber, and a backup so the internet never goes down", {"requested_products": ["P04"], "needs": ["uptime"]}),
    ("Do I need GST for WhatsApp?", {}),                                           # a question is not a statement
    ("I don't need cameras, just internet", {}),                                   # negated need is ignored
    ("कैमरा नहीं चाहिए", {}),
    ("Interested in WhatsApp orders", {"needs": ["whatsapp_customers"]}),         # "in WhatsApp" is not a city
])
def test_certain_facts(text, expected):
    st = State()
    got = chat._certain_facts(st, text)
    got.pop("business_type", None)
    assert got == expected


def test_certain_facts_never_override_recorded_values():
    st = State()
    dispatch("update_profile", {"city": "Mumbai", "employee_count": 6, "needs": ["cctv"]}, st)
    got = chat._certain_facts(st, "Sorry, the office is actually in Nashik with 9 people and we need cameras")
    assert "city" not in got and "employee_count" not in got and "needs" not in got


def test_guard_allows_names_from_the_offered_alternative():
    st = State()
    _known(st, business_type="Salon", city="Jaipur", needs=["services_only", "cctv"])
    alt = dispatch("get_recommendation", {}, st)["alternative_with_accel_line"]
    name = next(b["name"] for b in alt["bundle"] if b["id"] != "P23")
    text = f"Cloud CCTV runs only on our line; with {name} it comes to ₹{alt['monthly_from']:,} per month."
    assert chat._guard(text, st) == text and not st.warnings


def test_cancelled_gstin_survives_a_has_gstin_false_from_the_model():
    st = State()
    _known(st, business_type="Coaching centre", employee_count=6, city="Kochi", gstin="32HJJXE5083Y1ZR", requested_products=["P13"])
    r = dispatch("update_profile", {"has_gstin": False}, st)
    assert st.profile.gstin == "32HJJXE5083Y1ZR" and st.profile.gstin_status == "Cancelled" and "kept_gstin" in r
    rec = dispatch("get_recommendation", {}, st)
    assert {e["id"]: e["reason"] for e in rec["excluded"]}["P13"] == "GSTIN_NOT_ACTIVE"
    st2 = State()
    _known(st2, has_gstin=True)
    dispatch("update_profile", {"has_gstin": False}, st2)                 # no GSTIN on record: a plain correction still works
    assert st2.profile.has_gstin is False


def test_guard_does_not_flag_names_inside_bundled_product_descriptions():
    st = State()
    _known(st, business_type="Coaching centre", employee_count=12, city="Kolkata", has_gstin=True, no_specific_need=True)
    dispatch("get_recommendation", {}, st)
    assert "P02" in {i.product_id for i in st.recommendation.items}
    text = "Biz Fibre 300 – 300 Mbps fibre, unlimited data, Static IP optional."
    assert chat._guard(text, st) == text and not st.warnings


def test_certain_facts_fill_a_generic_business_type_when_the_model_misses_it():
    st = State()
    got = chat._certain_facts(st, "दिल्ली में साड़ी की दुकान, पाँच लोग, दो दुकानें, GST है। कार्ड मशीन बार-बार बंद होती है।")
    assert got["business_type"] == "sari shop" and got["employee_count"] == 5 and got["num_sites"] == 2
    assert got["city"] == "Delhi" and got["has_gstin"] is True and "pos_drops" in got["needs"]
    st2 = State()
    dispatch("update_profile", {"business_type": "Saree retail"}, st2)
    assert "business_type" not in chat._certain_facts(st2, "मेरी साड़ी की दुकान है")       # never overrides
