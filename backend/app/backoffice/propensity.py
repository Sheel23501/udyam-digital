"""Propensity-to-activate model for the back-office queue (Phase 9 stretch).

Logistic regression on the historical leads file: P(activated | what we knew about the lead). Deliberately simple and
transparent: coefficients double as the "why" shown to the field team. Leakage is avoided on purpose:
- drop_reason is NOT a feature (only dropped leads have one);
- stage_reached and follow-up calls are not features either (post-contact), so the score works for a brand-new lead.
The trained pipeline is saved to data/propensity.joblib (gitignored); data/propensity_meta.json (committed) carries
the metrics and coefficients so the numbers in the deck are reproducible."""
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ..config import DATA_DIR
from ..data.loader import connect

MODEL_PATH = Path(DATA_DIR) / "propensity.joblib"
META_PATH = Path(DATA_DIR) / "propensity_meta.json"

CATEGORICAL = ["segment", "lead_source", "preferred_language", "current_internet", "city_tier"]
NUMERIC = ["log_employees", "num_sites", "has_gstin", "has_udyam", "log_spend", "n_products", "turnover_ord"]
# stage_ord / follow_up_calls are deliberately NOT features: they describe what happened after contact, so the score is a
# propensity at lead creation (usable on brand-new digital leads) rather than a proxy for "how far did sales get".
STAGE_ORD = {"Lead": 0, "Contacted": 1, "Needs assessed": 2, "Quote accepted": 3, "KYC complete": 4, "Activated": 4}
TURNOVER_ORD = {"< 40 lakh": 0, "40 lakh - 1.5 cr": 1, "1.5 - 5 cr": 2, "5 - 25 cr": 3, "25 - 100 cr": 4}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def features(row: dict) -> dict:
    """One lead (a smb_leads row, or a dict shaped like one) -> model features."""
    return {
        "segment": row.get("segment") or "unknown",
        "lead_source": row.get("lead_source") or "Digital journey",
        "preferred_language": row.get("preferred_language") or "Hindi",
        "current_internet": row.get("current_internet") or "unknown",
        "city_tier": str(row.get("city_tier") or "2"),
        "log_employees": math.log1p(max(0.0, _num(row.get("employee_count"), 1))),
        "num_sites": min(20.0, _num(row.get("num_sites"), 1)),
        "has_gstin": 1.0 if str(row.get("has_gstin")) in ("Y", "True", "true", "1") else 0.0,
        "has_udyam": 1.0 if str(row.get("has_udyam")) in ("Y", "True", "true", "1") else 0.0,
        "log_spend": math.log1p(max(0.0, _num(row.get("monthly_telecom_spend_inr")))),
        "n_products": float(len([p for p in str(row.get("products_of_interest") or "").split(";") if p])),
        "turnover_ord": float(TURNOVER_ORD.get(row.get("annual_turnover_band") or "", 1)),
        "stage_ord": float(STAGE_ORD.get(row.get("stage_reached") or "Lead", 0)),
        "follow_up_calls": min(10.0, _num(row.get("customer_follow_up_calls"))),
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([features(r) for r in rows])


def train(seed: int = 42, save: bool = True) -> dict:
    rows = [dict(r) for r in connect().execute("SELECT * FROM smb_leads").fetchall()]
    X = _frame(rows)
    y = np.array([1 if r["outcome"] == "Activated" else 0 for r in rows])
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL), ("num", StandardScaler(), NUMERIC)])
    pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced", random_state=seed))])
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)
    pipe.fit(Xtr, ytr)
    auc_test = float(roc_auc_score(yte, pipe.predict_proba(Xte)[:, 1]))
    pipe.fit(X, y)                                            # final model on everything
    auc_train = float(roc_auc_score(y, pipe.predict_proba(X)[:, 1]))
    names = list(pipe.named_steps["pre"].get_feature_names_out())
    coefs = pipe.named_steps["clf"].coef_[0]
    top = sorted(zip(names, coefs), key=lambda t: -abs(t[1]))[:15]
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": int(len(y)), "positives": int(y.sum()),
        "auc_holdout": round(auc_test, 3), "auc_train": round(auc_train, 3), "model": "LogisticRegression(C=0.5, balanced)",
        "features": CATEGORICAL + NUMERIC, "excluded_on_purpose": ["drop_reason (only dropped leads have one)", "stage_reached and follow-up calls (post-contact; score must work on a brand-new lead)"],
        "top_coefficients": [{"feature": n.replace("cat__", "").replace("num__", ""), "coef": round(float(c), 3)} for n, c in top],
    }
    if save:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, MODEL_PATH)
        META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _model.cache_clear()
    _model.pipe = pipe
    return meta


@lru_cache(maxsize=1)
def _model():
    if getattr(_model, "pipe", None) is not None:
        return _model.pipe
    if MODEL_PATH.exists():
        try:
            return joblib.load(MODEL_PATH)
        except Exception:  # noqa: BLE001 — stale pickle from another sklearn version: retrain
            pass
    train(save=True)
    return _model.pipe


def meta() -> dict | None:
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def score(row: dict) -> float:
    """P(activate) in [0, 1] for a lead-shaped dict."""
    p = float(_model().predict_proba(_frame([row]))[0, 1])
    return max(0.0, min(1.0, p))


def explain(row: dict, k: int = 3) -> list[str]:
    """Top contributions (feature x coefficient) for this lead, as short phrases."""
    pipe = _model()
    x = pipe.named_steps["pre"].transform(_frame([row]))
    x = x.toarray()[0] if hasattr(x, "toarray") else np.asarray(x)[0]
    names = pipe.named_steps["pre"].get_feature_names_out()
    contrib = sorted(zip(names, x * pipe.named_steps["clf"].coef_[0]), key=lambda t: -abs(t[1]))
    out = []
    for n, c in contrib[:k]:
        label = n.replace("cat__", "").replace("num__", "").replace("_", " ")
        out.append(f"{'raises' if c > 0 else 'lowers'} the chance: {label}")
    return out
