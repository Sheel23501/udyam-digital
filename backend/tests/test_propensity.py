"""Propensity model: trains deterministically, separates activations better than chance, scores sanely, and is used
by the back-office queue for historical leads."""
import pytest

from app.backoffice import leads, propensity
from app.data.loader import connect


@pytest.fixture(scope="module")
def meta(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("prop")
    propensity.MODEL_PATH = tmp / "p.joblib"
    propensity.META_PATH = tmp / "p.json"
    propensity._model.cache_clear()
    propensity._model.pipe = None
    return propensity.train(save=True)


def test_training_is_better_than_chance_and_reproducible(meta):
    assert meta["rows"] == 5000 and meta["positives"] == 368
    assert meta["auc_holdout"] >= 0.65, meta
    assert propensity.META_PATH.exists() and propensity.MODEL_PATH.exists()
    again = propensity.train(save=False)
    assert again["auc_holdout"] == meta["auc_holdout"]


def test_no_leakage_features(meta):
    assert "drop_reason" not in meta["features"] and "outcome" not in meta["features"]
    assert "stage_ord" not in meta["features"] and "follow_up_calls" not in meta["features"]


def test_scores_are_probabilities_and_gst_helps(meta):
    row = dict(connect().execute("SELECT * FROM smb_leads WHERE outcome='Dropped' AND has_gstin='N' LIMIT 1").fetchone())
    p_no = propensity.score(row)
    p_yes = propensity.score({**row, "has_gstin": "Y"})
    assert 0.0 <= p_no <= 1.0 and 0.0 <= p_yes <= 1.0
    assert p_yes > p_no
    why = propensity.explain(row)
    assert len(why) == 3 and all("the chance" in w for w in why)


def test_queue_uses_model_for_historical_leads(meta):
    rows = leads.sample_dropped(20)
    assert rows and all(0 <= r["score"] <= 1 for r in rows)
    d = leads.detail(rows[0]["id"])
    assert d["model"] == "propensity" and any("the chance" in r for r in d["reasons"])
    assert d["suggested_action"]
