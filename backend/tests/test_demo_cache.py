"""The three demo conversations must answer from the committed reply cache with the network dead.
Skips (never fails) until scripts/record_demo.py has recorded them, so CI stays green before the recording."""
import json
from pathlib import Path

import pytest

from app.advisor import cache, chat
from app.advisor.state import State

SCENARIOS = json.loads((Path(__file__).parent / "llm_scenarios" / "transcripts.json").read_text(encoding="utf-8"))
DEMO = [s for s in SCENARIOS if s.get("demo")]


def _recorded(sc: dict) -> bool:
    turns: list[str] = []
    st = State()
    for t in sc["turns"]:
        turns.append(t)
        st.set_language(chat.detect_language(t, st.language))
        if not cache.path(turns, st.language).exists():
            return False
    return True


@pytest.mark.parametrize("sc", DEMO, ids=[s["name"][:40] for s in DEMO])
def test_demo_conversation_is_served_from_cache_when_offline(sc, monkeypatch):
    if not _recorded(sc):
        pytest.skip("demo cache not recorded yet: run scripts/record_demo.py when LLM quota is available")
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    st = State()
    for turn in sc["turns"]:
        reply = chat.step(st, turn, use_cache=True)
        assert st.provider == "cache" and reply
    assert st.recommendation is not None
