#!/usr/bin/env python
"""Run transcript scenarios through the live advisor (LLM + rules engine) and assert on the engine result, not the prose.

Usage:  python scripts/run_llm_scenarios.py [folder-or-file ...] [--runs N] [--only SUBSTR] [--record] [-v] [--allow-offline]
                                             [--save docs/demo-transcripts.md] [--max-wait 120]
        default folder: tests/llm_scenarios

Scenario format (a JSON object, or a list of objects, per file):
  {
    "name": "6-staff tailor asks for a firewall",
    "turns": ["Tailoring shop in Delhi", "6 people", "one shop", "yes GST", "I want a managed firewall"],
    "expect_includes": ["P20"],                   # must all be in the final bundle
    "expect_includes_any": [["P01", "P04"]],      # at least one of each group
    "expect_excludes": {"P21": "MIN_EMPLOYEES"},  # excluded with exactly this reason
    "expect_not_includes": ["P21"],
    "expect_qty": {"P23": 4},
    "expect_profile": {"num_sites": 2},
    "expect_language": "hi",                      # language detected on the last turn
    "expect_recommendation": true,                # default true; false = the advisor must still be asking
    "demo": true                                  # include in --save output
  }
Every scenario is also re-validated with engine.validate(): a bundle that breaks any rule fails regardless of the
expectations. Judges: drop your own transcripts in a folder and point this script at it. Exit code 0 = all pass.
"""
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.advisor.chat import step  # noqa: E402
from app.advisor.state import State  # noqa: E402
from app.engine.bundles import validate  # noqa: E402


def load(paths: list[str]) -> list[dict]:
    files: list[str] = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "*.json"))) if os.path.isdir(p) else [p]
    out: list[dict] = []
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        out += data if isinstance(data, list) else [data]
    return out


def check(sc: dict, st: State) -> list[str]:
    problems: list[str] = []
    rec = st.recommendation
    if sc.get("expect_recommendation", True) and rec is None:
        return ["no recommendation was produced"]
    if not sc.get("expect_recommendation", True):
        if rec is not None:
            problems.append("recommendation produced although the advisor should still be asking")
        return problems
    got = {i.product_id: i.qty for i in rec.items}
    exc = {e.product_id: e.reason.value for e in rec.excluded}
    for pid in sc.get("expect_includes", []):
        if pid not in got:
            problems.append(f"missing {pid}")
    for group in sc.get("expect_includes_any", []):
        if not any(pid in got for pid in group):
            problems.append(f"none of {group} in bundle")
    for pid, reason in sc.get("expect_excludes", {}).items():
        if exc.get(pid) != reason:
            problems.append(f"{pid} expected excluded as {reason}, got {exc.get(pid, 'INCLUDED' if pid in got else 'absent')}")
    for pid in sc.get("expect_not_includes", []):
        if pid in got:
            problems.append(f"should not include {pid}")
    for pid, qty in sc.get("expect_qty", {}).items():
        if got.get(pid) != qty:
            problems.append(f"{pid} qty expected {qty}, got {got.get(pid)}")
    prof = st.profile.model_dump(mode="json")
    for k, v in sc.get("expect_profile", {}).items():
        if prof.get(k) != v:
            problems.append(f"profile.{k} expected {v!r}, got {prof.get(k)!r}")
    if "expect_language" in sc and st.language != sc["expect_language"]:
        problems.append(f"language expected {sc['expect_language']}, got {st.language}")
    v = validate(got, st.profile)
    if v.violations:
        problems.append("bundle violates rules: " + "; ".join(f"{x.product_id}:{x.reason.value}" for x in v.violations))
    return problems


def run_one(sc: dict, max_wait: float, record: bool, verbose: bool = False, allow_offline: bool = False) -> tuple[bool, list[str], State, list[tuple[str, str]]]:
    st = State()
    transcript: list[tuple[str, str]] = []
    for turn in sc["turns"]:
        before = len(st.messages)
        reply = step(st, turn, use_cache=record, max_wait_s=max_wait)
        transcript.append((turn, reply))
        print(f"   > {turn}")
        if verbose:
            for m in st.messages[before:]:
                for tc in m.get("tool_calls") or []:
                    who = "server" if tc["id"].startswith("auto_") else "model"
                    print(f"     [{who}] {tc['function']['name']}({tc['function']['arguments']})")
        print("   < " + reply.replace("\n", "\n     "))
        if st.provider in ("offline", "cache"):
            print(f"   !! reply served by {st.provider}")
    problems = check(sc, st)
    if st.provider == "offline" and not allow_offline:
        problems.append("provider offline: reply was generated without the LLM")
    return (not problems), problems, st, transcript


def save_transcripts(path: str, records: list[tuple[dict, State, list[tuple[str, str]]]]) -> None:
    lines = ["# Advisor demo transcripts", "", "Generated by `scripts/run_llm_scenarios.py --save`. Replies are verbatim model output;",
             "the bundle under each transcript is the rules-engine result the UI card is rendered from.", ""]
    for sc, st, transcript in records:
        lines.append(f"## {sc['name']}")
        lines.append("")
        for user, reply in transcript:
            lines.append(f"**Owner:** {user}")
            lines.append("")
            lines.append("**Advisor:** " + reply.replace("\n", "  \n"))
            lines.append("")
        if st.recommendation:
            r = st.recommendation
            items = ", ".join(f"{i.product_id}×{i.qty}" for i in r.items)
            exc = "; ".join(f"{e.product_id} ({e.reason.value})" for e in r.excluded) or "none"
            lines.append(f"_Engine result: {items} · from ₹{r.monthly_min:,}/mo · excluded: {exc} · provider: {st.provider} · "
                         f"{st.usage['calls']} LLM calls, {st.usage['prompt_tokens'] + st.usage['completion_tokens']:,} tokens_")
            lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"saved {len(records)} transcripts to {path}")


def main() -> int:
    argv = sys.argv[1:]
    runs, only, record, save, max_wait, verbose, allow_offline = 1, None, False, None, 120.0, False, False
    paths: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--runs":
            runs = int(argv[i + 1]); i += 2
        elif a == "--only":
            only = argv[i + 1]; i += 2
        elif a == "--record":
            record = True; i += 1
        elif a in ("-v", "--verbose"):
            verbose = True; i += 1
        elif a == "--allow-offline":                      # measure the no-LLM path: engine-only replies are not a failure
            allow_offline = True; i += 1
        elif a == "--save":
            save = argv[i + 1]; i += 2
        elif a == "--max-wait":
            max_wait = float(argv[i + 1]); i += 2
        else:
            paths.append(a); i += 1
    paths = paths or [str(Path(__file__).resolve().parents[1] / "tests" / "llm_scenarios")]
    scenarios = [s for s in load(paths) if not only or only.lower() in s["name"].lower()]
    if not scenarios:
        print("no scenarios matched"); return 1

    total_fail, total_calls, total_tokens, providers, warnings = 0, 0, 0, {}, 0
    saved: list[tuple[dict, State, list[tuple[str, str]]]] = []
    started = time.time()
    for run in range(1, runs + 1):
        if runs > 1:
            print(f"\n===== run {run}/{runs} =====")
        for sc in scenarios:
            print(f"\n## {sc['name']}")
            ok, problems, st, transcript = run_one(sc, max_wait, record, verbose, allow_offline)
            total_fail += not ok
            total_calls += st.usage["calls"]
            total_tokens += st.usage["prompt_tokens"] + st.usage["completion_tokens"]
            providers[st.provider] = providers.get(st.provider, 0) + 1
            warnings += len(st.warnings)
            if st.recommendation:
                r = st.recommendation
                print(f"   engine: items={{{', '.join(f'{x.product_id}:{x.qty}' for x in r.items)}}} from ₹{r.monthly_min:,}/mo"
                      f" excluded={{{', '.join(f'{e.product_id}:{e.reason.value}' for e in r.excluded)}}}")
            print(f"   usage: {st.usage['calls']} calls, {st.usage['prompt_tokens']:,}+{st.usage['completion_tokens']:,} tokens, "
                  f"server-initiated tools={st.usage.get('auto_calls', 0)}, provider={st.provider}")
            for w in st.warnings:
                print(f"   guard: {w}")
            print(f"   {'PASS' if ok else 'FAIL'}")
            for p in problems:
                print(f"   !! {p}")
            if save and (sc.get("demo") or only) and run == 1:
                saved.append((sc, st, transcript))
    n = len(scenarios) * runs
    print(f"\n{n - total_fail}/{n} passed · {total_calls} LLM calls · {total_tokens:,} tokens · providers={providers}"
          f" · guard warnings={warnings} · {time.time() - started:.0f}s")
    if save and saved:
        save_transcripts(save, saved)
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
