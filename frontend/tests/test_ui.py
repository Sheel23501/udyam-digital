"""Headless UI tests with Streamlit's AppTest. The backend runs in-process (API_MODE=inprocess) and the advisor in
offline mode, so the whole journey is exercised with no server and no network: language -> OTP -> chat -> card ->
quote toggles -> consent -> KYC (K11 FAIL, then K03 PASS) -> order -> tracker -> done."""
import os
import sys
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1]
os.environ["API_MODE"] = "inprocess"
os.environ["ADVISOR_OFFLINE"] = "1"
os.environ["UI_STREAM_DELAY_S"] = "0"
sys.path.insert(0, str(FRONT))

from streamlit.testing.v1 import AppTest  # noqa: E402

REQUIRED = ["identity_verification", "service_provisioning", "regulatory_kyc_record", "service_updates"]


def start(path: str = "app.py") -> AppTest:
    at = AppTest.from_file(str(FRONT / path), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def texts(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(c.value for c in at.caption)


def to_chat(at: AppTest, lang_key: str = "lang_en") -> AppTest:
    at.button(key=lang_key).click().run()
    assert at.session_state["step"] == "otp"
    at.text_input(key="phone").set_value("9876543210").run()
    at.button(key="send_otp").click().run()
    assert not at.exception and at.session_state["otp_sent"]
    at.text_input(key="otp_code").set_value("1234").run()
    at.button(key="verify_otp").click().run()
    assert not at.exception, at.exception
    assert at.session_state["step"] == "chat" and at.session_state["session_id"]
    assert len(at.session_state["transcript"]) == 1                # opening message, no API call spent
    return at


def test_language_screen_has_both_languages_and_no_backend_dependency():
    at = start()
    labels = {b.label for b in at.button}
    assert {"हिंदी", "English"} <= labels
    assert at.session_state["step"] == "language"


def test_otp_validation_messages():
    at = start()
    at.button(key="lang_en").click().run()
    at.text_input(key="phone").set_value("12345").run()
    at.button(key="send_otp").click().run()
    assert any("10-digit" in e.value for e in at.error)
    at.text_input(key="phone").set_value("9876543210").run()
    at.button(key="send_otp").click().run()
    at.text_input(key="otp_code").set_value("0000").run()
    at.button(key="verify_otp").click().run()
    assert any("1234" in e.value for e in at.error) and at.session_state["step"] == "otp"


def test_full_journey_english_with_sample_kyc():
    at = to_chat(start())
    at.chat_input(key="chat_box").set_value("Kirana store in Lucknow, 2 people, one shop, no GST. Customers order on WhatsApp.").run()
    assert not at.exception, at.exception
    rec = at.session_state.get("recommendation")
    assert rec, texts(at)
    ids = {b["id"] for b in rec["bundle"]}
    assert "P18" in ids and ids & {"P01", "P04"} and rec["excluded"][0]["id"] == "P15"
    assert "₹" in texts(at) and len(at.session_state["transcript"]) == 3

    at.button(key="to_quote").click().run()
    assert at.session_state["step"] == "quote" and not at.exception
    assert at.metric[0].value.startswith("₹")
    before = at.session_state["quote"]["price"]["monthly_min"]
    at.toggle(key="tg_P18").set_value(False).run()
    assert "P18" not in at.session_state["bundle_items"]
    assert at.session_state["quote"]["price"]["monthly_min"] == before - 299
    assert any(t.disabled for t in at.toggle if t.key == "ex_P15")           # excluded item shown locked

    at.button(key="to_consent").click().run()
    assert at.session_state["step"] == "consent"
    assert at.button(key="agree").disabled
    for pid in REQUIRED:
        at.checkbox(key=f"purpose_{pid}").check().run()
    assert not at.button(key="agree").disabled
    at.button(key="agree").click().run()
    assert at.session_state["step"] == "kyc" and at.session_state["consent_id"]

    at.radio(key="kyc_mode_radio").set_value("Use a sample applicant").run()
    at.selectbox(key="sample_pick").select("K11").run()
    at.button(key="verify_sample").click().run()
    assert not at.exception, at.exception
    assert at.session_state["kyc"]["verdict"] == "FAIL"
    body = texts(at)
    assert "Could not verify" in body and ("90 days" in body or "old" in body.lower())
    assert "ADDRESS_PROOF_STALE" in {c["code"] for c in at.session_state["kyc"]["checks"]}
    assert at.button(key="talk_human") is not None

    at.button(key="kyc_again").click().run()
    assert "kyc" not in at.session_state
    at.selectbox(key="sample_pick").select("K03").run()
    at.button(key="verify_sample").click().run()
    assert at.session_state["kyc"]["verdict"] == "PASS"
    assert "XXXXXXXXXX" in texts(at)                                            # masked GSTIN on screen, never raw

    at.button(key="place_order").click().run()
    assert not at.exception, at.exception
    assert at.session_state["step"] == "tracker" and at.session_state["order_id"].startswith("ORD-")
    assert at.progress[0].value == 0
    at.button(key="advance").click().run()
    assert not at.exception and at.progress[0].value > 0
    at.button(key="withdraw").click().run()
    assert at.session_state["consent_withdrawn"] and any("withdrawn" in s.value.lower() for s in at.success)
    at.button(key="finish").click().run()
    assert at.session_state["step"] == "done" and at.session_state["session_id"] in texts(at) + "".join(c.value for c in at.code)
    at.button(key="start_again").click().run()
    assert at.session_state["step"] == "language" and "session_id" not in at.session_state


def test_hindi_journey_to_card_and_language_toggle():
    at = to_chat(start(), "lang_hi")
    assert at.session_state["lang"] == "hi" and "नमस्ते" in at.session_state["transcript"][0]["text"]
    at.button(key="example_1").click().run()                                    # Hindi sari-shop example
    assert not at.exception, at.exception
    rec = at.session_state.get("recommendation")
    assert rec, texts(at)
    assert {b["id"] for b in rec["bundle"]} >= {"P09", "P19", "P23"}
    assert "प्रति माह" in texts(at)                                             # card labels in Hindi
    at.radio(key="lang_radio").set_value("English").run()
    assert at.session_state["lang"] == "en" and "per month" in texts(at)


def test_kyc_fail_can_hand_off_to_a_human():
    at = to_chat(start())
    at.chat_input(key="chat_box").set_value("Bakery in Surat, 5 staff, one shop, GST registered, just internet").run()
    assert at.session_state.get("recommendation")
    at.button(key="to_quote").click().run()
    at.button(key="to_consent").click().run()
    for pid in REQUIRED:
        at.checkbox(key=f"purpose_{pid}").check().run()
    at.button(key="agree").click().run()
    at.radio(key="kyc_mode_radio").set_value("Use a sample applicant").run()
    at.selectbox(key="sample_pick").select("K07").run()
    at.button(key="verify_sample").click().run()
    assert at.session_state["kyc"]["verdict"] == "FAIL"
    at.button(key="talk_human").click().run()
    assert at.session_state["step"] == "done" and at.session_state["handoff"]
    assert "call you" in texts(at).lower()


def test_backoffice_page_pin_queue_and_audit():
    at = start("pages/backoffice.py")
    at.text_input(key="staff_pin").set_value("0000").run()
    at.button(key="staff_enter").click().run()
    assert at.error and not at.session_state.get("staff_ok")
    at.text_input(key="staff_pin").set_value("1234").run()
    at.button(key="staff_enter").click().run()
    assert not at.exception, at.exception
    assert at.session_state["staff_ok"]
    assert at.dataframe, "queue dataframe missing"
    df = at.dataframe[0].value
    assert len(df) > 0 and {"score", "suggested_action", "est_monthly_value"} <= set(df.columns)
    assert (df["score"].between(0, 1)).all()
