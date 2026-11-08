#!/usr/bin/env python
"""Train the propensity-to-activate model on smb_leads and print its metrics and top coefficients.

Usage: python scripts/train_propensity.py
Writes data/propensity.joblib (gitignored) and data/propensity_meta.json (committed: metrics for the deck)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backoffice import propensity  # noqa: E402


def main() -> int:
    m = propensity.train(save=True)
    print(f"rows={m['rows']} activated={m['positives']}  AUC holdout={m['auc_holdout']}  AUC train={m['auc_train']}")
    print("top coefficients (positive = more likely to activate):")
    for c in m["top_coefficients"]:
        print(f"  {c['coef']:+.3f}  {c['feature']}")
    print(f"\nsaved {propensity.MODEL_PATH.name} and {propensity.META_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
