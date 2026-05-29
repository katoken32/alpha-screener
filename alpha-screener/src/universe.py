"""Build the tradable US universe.

Source: NASDAQ Trader symbol directory (covers NASDAQ + NYSE/AMEX/ARCA).
These are public, pipe-delimited text files. We keep common stock, drop test
issues, optionally drop ETFs, and strip odd symbol classes (warrants, units).

Network note: this hits ftp.nasdaqtrader.com over HTTP. It works fine on a
GitHub Actions runner (open internet). If it ever fails, we fall back to a
small built-in seed list so the pipeline still runs.
"""
from __future__ import annotations
import io
import re
import requests
import pandas as pd

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Tiny fallback so the pipeline never hard-fails on a network hiccup.
_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "MU", "ARM",
    "AAOI", "AMD", "MRVL", "TSM", "COHR", "ASML", "PLTR", "TSLA", "NFLX",
]

_BAD_SUFFIX = re.compile(r"[.$^]")  # warrants/units/preferred markers


def _download(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="|")
    # Last row is a "File Creation Time" footer -> drop rows with NaN symbol.
    df = df[~df.iloc[:, 0].astype(str).str.contains("File Creation Time", na=False)]
    return df


def build_universe(exclude_etfs: bool = True) -> list[str]:
    """Return a de-duplicated list of US common-stock tickers."""
    try:
        nas = _download(NASDAQ_LISTED)
        oth = _download(OTHER_LISTED)
    except Exception as e:  # noqa: BLE001
        print(f"[universe] symbol download failed ({e}); using fallback list")
        return _FALLBACK

    syms: list[str] = []

    # nasdaqlisted: Symbol|Security Name|Market Category|Test Issue|...|ETF|...
    n = nas.copy()
    n = n[n["Test Issue"] == "N"]
    if exclude_etfs and "ETF" in n.columns:
        n = n[n["ETF"] != "Y"]
    syms += n["Symbol"].astype(str).tolist()

    # otherlisted: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|...|Test Issue|...
    o = oth.copy()
    if "Test Issue" in o.columns:
        o = o[o["Test Issue"] == "N"]
    if exclude_etfs and "ETF" in o.columns:
        o = o[o["ETF"] != "Y"]
    sym_col = "ACT Symbol" if "ACT Symbol" in o.columns else o.columns[0]
    syms += o[sym_col].astype(str).tolist()

    # Clean: drop blanks, odd classes, and 5th-letter non-common share codes.
    clean = []
    seen = set()
    for s in syms:
        s = s.strip().upper()
        if not s or _BAD_SUFFIX.search(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        clean.append(s)

    print(f"[universe] {len(clean)} tickers after cleaning")
    return clean or _FALLBACK


if __name__ == "__main__":
    u = build_universe()
    print(u[:25], "..." if len(u) > 25 else "")
