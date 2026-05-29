"""Data access via yfinance (free).

Two very different cost profiles:
  * get_price_matrix(): ONE batched call per chunk -> fast, used for the whole
    universe.
  * get_fundamentals(): one slow, flaky request PER ticker -> only ever called
    on the few hundred survivors of the momentum gate.

yfinance scrapes Yahoo; it is not an official API. Expect occasional missing
tickers and transient failures. Everything here degrades gracefully (skips the
bad ticker rather than crashing the run).
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
import yfinance as yf


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def get_price_matrix(tickers: list[str], period: str = "2y", chunk_size: int = 150):
    """Return (close_df, volume_df) with dates as index, tickers as columns.

    Uses auto_adjust=True so 'Close' is split/dividend adjusted.
    """
    closes, vols = [], []
    for ci, chunk in enumerate(_chunks(tickers, chunk_size)):
        try:
            data = yf.download(
                chunk,
                period=period,
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[data] chunk {ci} download failed ({e}); skipping")
            continue

        for t in chunk:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    sub = data[t]
                else:  # single-ticker chunk: flat columns
                    sub = data
                c = sub["Close"].rename(t)
                v = sub["Volume"].rename(t)
                if c.dropna().shape[0] >= 250:  # need ~1y of data minimum
                    closes.append(c)
                    vols.append(v)
            except Exception:  # noqa: BLE001
                continue
        time.sleep(0.5)  # be gentle with Yahoo

    if not closes:
        raise RuntimeError("no price data downloaded")
    close_df = pd.concat(closes, axis=1).sort_index()
    vol_df = pd.concat(vols, axis=1).sort_index()
    print(f"[data] price matrix: {close_df.shape[1]} tickers x {close_df.shape[0]} days")
    return close_df, vol_df


def _row(df: pd.DataFrame, *names) -> pd.Series | None:
    """Find a financial-statement row by trying several label spellings."""
    if df is None or df.empty:
        return None
    idx = {str(i).lower(): i for i in df.index}
    for n in names:
        key = n.lower()
        for label_l, label in idx.items():
            if key in label_l:
                return df.loc[label]
    return None


def get_fundamentals(ticker: str) -> dict:
    """Best-effort quarterly fundamentals for ONE ticker.

    Free data gives ~4-5 quarters, so YoY/acceleration is limited. We compute
    what we can and leave the rest NaN. Documented limitation, not a bug.
    """
    out = {
        "ticker": ticker,
        "rev_growth": np.nan,    # most recent YoY (or QoQ fallback)
        "rev_accel": np.nan,     # latest YoY minus prior YoY
        "eps_growth": np.nan,
        "gross_margin": np.nan,
        "sector": None,
    }
    try:
        t = yf.Ticker(ticker)
        q = t.quarterly_income_stmt  # columns newest-first
    except Exception:  # noqa: BLE001
        return out
    if q is None or q.empty:
        return out
    q = q.reindex(sorted(q.columns), axis=1)  # oldest -> newest
    rev = _row(q, "Total Revenue", "Revenue")
    gp = _row(q, "Gross Profit")
    eps = _row(q, "Diluted EPS", "Basic EPS")
    ni = _row(q, "Net Income")

    def yoy(series):
        s = series.dropna()
        if len(s) >= 5 and s.iloc[-5] not in (0, np.nan):
            return s.iloc[-1] / s.iloc[-5] - 1
        if len(s) >= 2 and s.iloc[-2] not in (0, np.nan):
            return s.iloc[-1] / s.iloc[-2] - 1  # QoQ fallback
        return np.nan

    if rev is not None:
        out["rev_growth"] = yoy(rev)
        s = rev.dropna()
        if len(s) >= 6 and s.iloc[-6] not in (0, np.nan):
            prior_yoy = s.iloc[-2] / s.iloc[-6] - 1
            if not np.isnan(out["rev_growth"]):
                out["rev_accel"] = out["rev_growth"] - prior_yoy
    eps_or_ni = eps if eps is not None else ni
    if eps_or_ni is not None:
        out["eps_growth"] = yoy(eps_or_ni)
    if gp is not None and rev is not None:
        try:
            out["gross_margin"] = float(gp.dropna().iloc[-1] / rev.dropna().iloc[-1])
        except Exception:  # noqa: BLE001
            pass
    try:
        out["sector"] = t.info.get("sector")
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    return out
