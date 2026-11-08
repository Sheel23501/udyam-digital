#!/usr/bin/env python
"""Record (or check) the demo conversations in the advisor reply cache, so the demo survives a dead or throttled API.

  python scripts/record_demo.py                 replay every scenario flagged "demo": true through the LIVE advisor with
                                                caching on; print which turns a model answered (now cached) and which fell
                                                to the offline path (NOT cached: re-run when quota is back)
  python scripts/record_demo.py --check         replay with ADVISOR_OFFLINE=1 and verify every turn is served from cache
  python scripts/record_demo.py --only hindi    filter scenarios by name

Cache entries live in data/cache/advisor/ (gitignored); commit the demo ones with the `git add -f` line this prints.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.advisor import cache  # noqa: E402
from app.advisor.chat import step  # noqa: E402
from app.advisor.state import State  # noqa: E402

SCENARIOS = ROOT / "tests" / "llm_scenarios" / "transcripts.json"


def demo_scenarios(only: str | None) -> list[dict]:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return [s for s in data if s.get("demo") and (not only or only.lower() in s["name"].lower())]


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    max_wait = float(argv[argv.index("--max-wait") + 1]) if "--max-wait" in argv else 180.0
    if check:
        os.environ["ADVISOR_OFFLINE"] = "1"
    files: list[Path] = []
    missing = 0
    for sc in demo_scenarios(only):
        print(f"\n## {sc['name']}")
        st = State()
        for turn in sc["turns"]:
            reply = step(st, turn, use_cache=True, max_wait_s=max_wait)
            p = cache.path(st.user_turns, st.language)
            cached = p.exists()
            tag = st.provider or "?"
            if check:
                ok = st.provider == "cache"
                missing += not ok
                print(f"   {'✓' if ok else '✗'} {turn[:60]!r} -> {tag}")
            else:
                ok = st.provider not in ("offline", None)
                missing += not ok
                print(f"   {'✓ cached ' if ok else '✗ offline'} {turn[:60]!r} -> {tag}")
                print("     " + reply.replace("\n", "\n     ")[:300])
            if cached:
                files.append(p)
    print()
    if check:
        print(f"{'all demo turns served from cache' if not missing else f'{missing} turn(s) NOT in cache'}")
        return 1 if missing else 0
    print(f"{missing} turn(s) fell to the offline path and were not cached; re-run when the LLM quota is back." if missing else "every turn cached.")
    if files:
        rel = " ".join(str(f.relative_to(ROOT.parent)) for f in dict.fromkeys(files))
        print(f"\ncommit the demo cache with:\n  git add -f {rel}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
