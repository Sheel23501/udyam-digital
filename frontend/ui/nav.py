"""Step router helpers."""
import streamlit as st

STEPS = ["language", "otp", "chat", "quote", "consent", "kyc", "tracker", "done"]


def go(step: str) -> None:
    st.session_state.step = step
    st.rerun()


def set_step(step: str) -> None:
    """For use inside widget callbacks (st.rerun is not allowed there)."""
    st.session_state.step = step


def reset() -> None:
    keep = {"lang", "partner", "ref"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]
    st.session_state.step = "language"
