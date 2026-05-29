"""Offline sanity tests (no network). Run: python -m pytest tests/ -q
or simply: python tests/test_factors.py
"""
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src import factors, scoring


def _synthetic(n_days=400, n_tk=20, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n_days, freq="B")
    tks = [f"T{i:02d}" for i in range(n_tk)]
    # give ticker i a deterministic drift so ranks are predictable
    drift = np.linspace(-0.001, 0.002, n_tk)
    rets = rng.normal(0, 0.02, (n_days, n_tk)) + drift
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tks)
    vol = pd.DataFrame(rng.integers(1_000_000, 5_000_000, (n_days, n_tk)), index=dates, columns=tks)
    return close, vol


def test_price_factors_shape_and_rank():
    close, vol = _synthetic()
    pf = factors.price_factors(close, vol)
    assert set(["momentum", "rs_rank", "trend_ok", "dist_high"]).issubset(pf.columns)
    assert pf["rs_rank"].between(0, 100).all()
    # highest-drift ticker should rank near the top on momentum
    assert pf["momentum"].idxmax() in ("T19", "T18", "T17")
    print("test_price_factors_shape_and_rank OK")


def test_momentum_gate_subset():
    close, vol = _synthetic()
    pf = factors.price_factors(close, vol)
    cfg = {"rs_rank_min": 50, "within_high_pct": 90, "vol_surge_min": 0.0,
           "require_uptrend": False}
    surv = factors.apply_momentum_gate(pf, cfg)
    assert len(surv) <= len(pf)
    assert (surv["rs_rank"] >= 50).all()
    print("test_momentum_gate_subset OK")


def test_zscore_and_composite():
    close, vol = _synthetic()
    pf = factors.price_factors(close, vol)
    fund = pd.DataFrame({
        "growth_raw": np.linspace(-0.1, 0.5, len(pf)),
        "quality_raw": np.linspace(0.2, 0.7, len(pf)),
    }, index=pf.index)
    weights = {"momentum": 0.45, "trend": 0.15, "growth": 0.25, "quality": 0.15}
    ranked = scoring.composite_score(pf, fund, weights)
    assert "score" in ranked.columns
    assert ranked["score"].is_monotonic_decreasing
    z = scoring.zscore(pd.Series([1, 2, 3, 100.0]))
    assert z.max() <= 3.0 and z.min() >= -3.0  # clipping works
    print("test_zscore_and_composite OK")


if __name__ == "__main__":
    test_price_factors_shape_and_rank()
    test_momentum_gate_subset()
    test_zscore_and_composite()
    print("\nAll tests passed.")
