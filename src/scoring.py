"""Composite scoring: robust z-score each factor, weight, sum, rank."""
from __future__ import annotations
import numpy as np
import pandas as pd


def zscore(s: pd.Series, clip: float = 3.0) -> pd.Series:
    """Cross-sectional z-score with outlier clipping. NaNs -> 0 (neutral)."""
    s = s.astype(float)
    mu = s.mean(skipna=True)
    sd = s.std(skipna=True)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    z = (s - mu) / sd
    return z.clip(-clip, clip).fillna(0.0)


def composite_score(survivors: pd.DataFrame, fund: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Combine momentum/trend (price) + growth/quality (fundamental).

    `survivors` indexed by ticker with price-factor columns.
    `fund` indexed by ticker with growth_raw/quality_raw.
    """
    df = survivors.join(fund, how="left")

    z_mom = zscore(df["momentum"])
    z_trend = zscore(df["rs_rank"])  # use RS rank as the trend/leadership proxy
    z_growth = zscore(df.get("growth_raw", pd.Series(np.nan, index=df.index)))
    z_quality = zscore(df.get("quality_raw", pd.Series(np.nan, index=df.index)))

    df["z_momentum"] = z_mom
    df["z_trend"] = z_trend
    df["z_growth"] = z_growth
    df["z_quality"] = z_quality

    df["score"] = (
        weights["momentum"] * z_mom
        + weights["trend"] * z_trend
        + weights["growth"] * z_growth
        + weights["quality"] * z_quality
    )
    return df.sort_values("score", ascending=False)
