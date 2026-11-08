#!/usr/bin/env python
"""Run Smart KYC over a folder of applicant images and print the verdict table.

Usage:  python scripts/kyc_report.py [folder] [--no-cache] [--key tests/kyc_answer_key_images.json]
Files are expected as <APPLICANT>_<doc_type>.png with doc_type in
gst_certificate | udyam_certificate | signatory_id | address_proof   (e.g. K07_gst_certificate.png).
Per-applicant JSON reports are written to data/cache/reports/. Exit code 0 unless --key is given and a verdict differs.
"""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import CACHE_DIR  # noqa: E402
from app.kyc.images import run_images  # noqa: E402
from app.kyc.schemas import DOC_TYPES  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    key = None
    if "--key" in argv:
        i = argv.index("--key")
        key = json.loads(Path(argv[i + 1]).read_text(encoding="utf-8"))
        argv = argv[:i] + argv[i + 2:]
    use_cache = "--no-cache" not in argv
    args = [a for a in argv if not a.startswith("--")]
    folder = args[0] if args else str(Path(__file__).resolve().parents[1] / "data" / "kyc_documents")
    out_dir = Path(CACHE_DIR) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(glob.glob(os.path.join(folder, "*.png")) + glob.glob(os.path.join(folder, "*.jpg")))
    apps: dict[str, dict[str, str]] = {}
    for p in paths:
        stem = Path(p).stem
        if "_" not in stem:
            continue
        app, doc_type = stem.split("_", 1)
        if doc_type in DOC_TYPES:
            apps.setdefault(app, {})[doc_type] = p

    mismatches = 0
    print(f"{'App':5s} {'Verdict':8s} {'GSTIN (masked)':17s} Findings")
    errors = 0
    for app in sorted(apps):
        try:
            r = run_images(app, apps[app], use_cache=use_cache)
        except Exception as e:                       # noqa: BLE001 — keep going; one quota error must not hide the rest
            errors += 1
            print(f"{app:5s} {'ERROR':8s} {'-':17s} {str(e).splitlines()[0][:110]}")
            continue
        (out_dir / f"{app}.json").write_text(r.model_dump_json(indent=2), encoding="utf-8")
        flags = [f"{c.code}" for c in r.checks if c.status in ("FAIL", "REVIEW")]
        warns = [c.code for c in r.checks if c.status == "WARN"]
        line = f"{app:5s} {r.verdict:8s} {r.masked.get('gstin', '-'):17s} {', '.join(flags) or '-'}" + (f"  (warn: {', '.join(warns)})" if warns else "")
        if key and app in key:
            exp = key[app]
            ok = r.verdict == exp["verdict"] and set(exp.get("codes", [])) <= set(flags)
            mismatches += not ok
            line += "   ✓" if ok else f"   ✗ expected {exp['verdict']} {exp.get('codes', [])}"
        print(line)
    print(f"\n{len(apps)} applicants ({errors} could not be processed); reports in {out_dir}")
    if key:
        print(f"{len(apps) - mismatches - errors}/{len(apps)} match the answer key")
    return 1 if (mismatches or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
