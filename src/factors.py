"""Factor calculations.

Price factors are point-in-time safe: they only use prices up to the eval date,
so the same functions are reused by backtest.py. Fundamental factors come from
free data that is NOT point-in-time, so they are excluded from the backtest and
used live-only (documented limitation).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


def price_factors(close: pd.DataFrame, volume: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Cross-sectional price factors as of `asof` (default: last row).

    Returns one row per ticker with raw factor values + screen booleans.
    """
    if asof is not None:
        close = close.loc[:asof]
        volume = volume.loc[:asof]
    if len(close) < TRADING_DAYS["12m"] + 5:
        # not enough history; use what we have but 12m may be NaN
        pass

    px = close.iloc[-1]

    def ret(days):
        if len(close) <= days:
            return pd.Series(np.nan, index=close.columns)
        return close.iloc[-1] / close.iloc[-1 - days] - 1

    mom_3m = ret(TRADING_DAYS["3m"])
    mom_6m = ret(TRADING_DAYS["6m"])
    mom_12m = ret(TRADING_DAYS["12m"])
    # Blended momentum, "12-1" style (skip most recent month reduces reversal).
    mom_12_1 = (close.iloc[-1] / close.iloc[-1 - TRADING_DAYS["12m"]]) / \
               (close.iloc[-1] / close.iloc[-1 - TRADING_DAYS["1m"]]) - 1 \
               if len(close) > TRADING_DAYS["12m"] + 1 else pd.Series(np.nan, index=close.columns)
    momentum = pd.concat([mom_6m, mom_12_1], axis=1).mean(axis=1)

    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    ma50_prev = close.rolling(50).mean().iloc[-6] if len(close) > 56 else pd.Series(np.nan, index=close.columns)
    high_252 = close.rolling(252, min_periods=60).max().iloc[-1]
    dist_high = px / high_252  # 1.0 == at high

    vol20 = volume.rolling(20).mean().iloc[-1]
    vol50 = volume.rolling(50).mean().iloc[-1]
    vol_surge = vol20 / vol50
    dollar_vol = (px * vol20)

    trend_ok = (px > ma50) & (ma50 > ma200) & (ma50 > ma50_prev)

    df = pd.DataFrame({
        "price": px,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
        "momentum": momentum,
        "dist_high": dist_high,
        "vol_surge": vol_surge,
        "dollar_vol": dollar_vol,
        "trend_ok": trend_ok.fillna(False),
    })
    # cross-sectional relative-strength rank on blended momentum
    df["rs_rank"] = df["momentum"].rank(pct=True) * 100
    return df


def apply_universe_filter(pf: pd.DataFrame, min_price: float, min_dollar_volume: float) -> pd.DataFrame:
    return pf[(pf["price"] >= min_price) & (pf["dollar_vol"] >= min_dollar_volume)]


def apply_momentum_gate(pf: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Layer 2 gate -> survivors that earn a (slow) fundamental fetch."""
    m = pf["rs_rank"] >= cfg["rs_rank_min"]
    m &= pf["dist_high"] >= (1 - cfg["within_high_pct"] / 100.0)
    m &= pf["vol_surge"] >= cfg["vol_surge_min"]
    if cfg.get("require_uptrend", True):
        m &= pf["trend_ok"]
    return pf[m].copy()


def fundamental_factors(rows: list[dict]) -> pd.DataFrame:
    """Assemble per-ticker fundamentals into growth/quality raw inputs."""
    df = pd.DataFrame(rows).set_index("ticker")
    # growth: revenue growth + acceleration + eps growth (equal blend of available)
    df["growth_raw"] = df[["rev_growth", "rev_accel", "eps_growth"]].mean(axis=1)
    # quality: gross margin level
    df["quality_raw"] = df["gross_margin"]
    return df
