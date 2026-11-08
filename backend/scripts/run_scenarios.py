#!/usr/bin/env python
"""Run profile-based advisor scenarios through the rules engine and report pass/fail.

Usage:  python scripts/run_scenarios.py [folder-or-file ...]      (default: tests/scenarios)

Scenario format (a JSON object, or a JSON list of objects, per file):
  {
    "name": "kirana no GSTIN wants WhatsApp API",
    "profile": {"business_type": "Kirana store", "employee_count": 2, "num_sites": 1, "city": "Lucknow",
                "has_gstin": false, "needs": ["whatsapp_customers"], "requested_products": []},
    "expect_includes":     ["P04", "P07", "P18"],            # must all be in the bundle
    "expect_excludes":     {"P15": "GSTIN_REQUIRED"},         # must be excluded with exactly this reason
    "expect_not_includes": ["P15"]                            # must not be in the bundle
  }
Judges: drop your own files in a folder and point this script at it. Exit code 0 = all pass.
"""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.bundles import recommend, validate  # noqa: E402
from app.engine.models import Profile  # noqa: E402


def load(paths: list[str]) -> list[dict]:
    files: list[str] = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "*.json"))) if os.path.isdir(p) else [p]
    out: list[dict] = []
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        out += data if isinstance(data, list) else [data]
    return out


def run(sc: dict) -> tuple[bool, list[str], dict]:
    prof = Profile(**sc["profile"])
    b = recommend(prof)
    got = {i.product_id: i.qty for i in b.items}
    exc = {e.product_id: e.reason.value for e in b.excluded}
    problems: list[str] = []
    for pid in sc.get("expect_includes", []):
        if pid not in got:
            problems.append(f"missing {pid}")
    for pid, reason in sc.get("expect_excludes", {}).items():
        if exc.get(pid) != reason:
            problems.append(f"{pid} expected excluded as {reason}, got {exc.get(pid, 'INCLUDED' if pid in got else 'absent')}")
    for pid in sc.get("expect_not_includes", []):
        if pid in got:
            problems.append(f"should not include {pid}")
    v = validate(got, prof)
    if v.violations:
        problems.append("bundle violates rules: " + "; ".join(f"{x.product_id}:{x.reason.value}" for x in v.violations))
    return (not problems), problems, {"segment": b.segment, "items": got, "excluded": exc, "monthly_from": b.monthly_min, "notes": [n.detail for n in b.notes]}


def main() -> int:
    paths = sys.argv[1:] or [str(Path(__file__).resolve().parents[1] / "tests" / "scenarios")]
    scenarios = load(paths)
    fails = 0
    for sc in scenarios:
        ok, problems, summary = run(sc)
        fails += not ok
        flag = "PASS" if ok else "FAIL"
        print(f"{flag}  {sc['name']}")
        print(f"      seg={summary['segment']}  items={summary['items']}  from ₹{summary['monthly_from']:,}/mo")
        if summary["excluded"]:
            print(f"      excluded={summary['excluded']}")
        if summary["notes"]:
            print(f"      notes={summary['notes']}")
        for p in problems:
            print(f"      !! {p}")
    print(f"\n{len(scenarios) - fails}/{len(scenarios)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
