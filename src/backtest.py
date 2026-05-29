"""Backtest / coefficient tuning for the PRICE factors.

Why price-only: free data is not point-in-time for fundamentals, so backtesting
growth/quality on it would bake in look-ahead + survivorship bias ("clean
garbage"). We rigorously test only what we can: the price/momentum factors,
which use adjusted prices up to each rebalance date.

Method (correct for a *ranking* system, not a trade simulator):
  - Walk forward monthly.
  - At each date compute factors from history up to that date only.
  - Measure IC = Spearman rank corr(factor, next-month return).
  - Build top/bottom quintile spread.
A positive, stable IC (and a positive quintile spread) is evidence the factor
ranks future winners. Use the weight grid to pick momentum/trend weights that
maximize IC information ratio, then transfer to config.yaml.

Usage:
  python -m src.backtest --tickers AAPL MSFT NVDA ...      (or --sp500)
"""
from __future__ import annotations
import argparse
import itertools
import numpy as np
import pandas as pd

from . import data, factors
from .scoring import zscore


def _monthly_dates(close: pd.DataFrame):
    return close.resample("ME").last().index


def factor_panel(close, vol):
    """Compute momentum + rs_rank at each month-end (point-in-time)."""
    dates = _monthly_dates(close)
    recs = []
    for d in dates:
        hist = close.loc[:d]
        if len(hist) < 260:
            continue
        pf = factors.price_factors(close, vol, asof=d)
        recs.append((d, pf[["momentum", "rs_rank"]]))
    return recs


def evaluate(close, vol, w_mom=0.75, w_trend=0.25):
    """Return IC series and quintile spread for a momentum/trend blend."""
    panel = factor_panel(close, vol)
    fwd = close.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    ics, spreads = [], []
    for i, (d, pf) in enumerate(panel[:-1]):
        nxt = panel[i + 1][0]
        if nxt not in fwd.index:
            continue
        score = w_mom * zscore(pf["momentum"]) + \
                w_trend * zscore(pf["rs_rank"])
        r = fwd.loc[nxt].reindex(score.index)
        ok = score.notna() & r.notna()
        if ok.sum() < 10:
            continue
        ics.append(score[ok].corr(r[ok], method="spearman"))
        q = pd.qcut(score[ok].rank(method="first"), 5, labels=False)
        spreads.append(r[ok][q == 4].mean() - r[ok][q == 0].mean())
    ic = pd.Series(ics)
    return {
        "ic_mean": ic.mean(),
        "ic_ir": ic.mean() / ic.std() if ic.std() else np.nan,
        "quintile_spread_mean": np.nanmean(spreads) if spreads else np.nan,
        "n_periods": len(ics),
    }


def grid_search(close, vol):
    print("w_mom  w_trend |  IC    IC_IR  Q5-Q1spread  n")
    best = None
    for w_mom in np.arange(0.0, 1.01, 0.25):
        w_trend = 1 - w_mom
        m = evaluate(close, vol, w_mom, w_trend)
        print(f"{w_mom:4.2f}   {w_trend:4.2f}  | {m['ic_mean']:+.3f}  "
              f"{m['ic_ir']:+.2f}   {m['quintile_spread_mean']:+.3%}    {m['n_periods']}")
        if best is None or (m["ic_ir"] or -9) > (best[1]["ic_ir"] or -9):
            best = ((w_mom, w_trend), m)
    print(f"\nBest by IC_IR: w_mom={best[0][0]}, w_trend={best[0][1]}")
    return best


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None)
    args = ap.parse_args()
    tk = args.tickers or ["AAPL", "MSFT", "NVDA", "AMD", "MU", "ARM", "AVGO",
                          "MRVL", "AAOI", "PLTR", "META", "GOOGL", "AMZN", "TSLA"]
    close, vol = data.get_price_matrix(tk, period="5y", chunk_size=150)
    grid_search(close, vol)
