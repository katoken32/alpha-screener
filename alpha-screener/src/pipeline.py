"""Daily run: universe -> price factors -> momentum gate -> fundamentals on
survivors -> composite score -> email.

Run locally:   python -m src.pipeline
On CI:         invoked by .github/workflows/daily.yml
Env flags:     DRY_RUN=1 skips sending email (prints top rows instead)
"""
from __future__ import annotations
import os
import yaml
import pandas as pd

from . import universe, data, factors, scoring, email_report


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def check_regime(cfg: dict) -> bool:
    try:
        c, _ = data.get_price_matrix([cfg["regime"]["index"]], period="2y", chunk_size=1)
        idx = c.iloc[:, 0]
        return bool(idx.iloc[-1] > idx.rolling(cfg["regime"]["ma"]).mean().iloc[-1])
    except Exception as e:  # noqa: BLE001
        print(f"[regime] check failed ({e}); assuming neutral=True")
        return True


def run(cfg: dict) -> pd.DataFrame:
    # 1. Universe
    tickers = universe.build_universe(exclude_etfs=cfg["universe"]["exclude_etfs"])
    if cfg["universe"].get("max_tickers"):
        tickers = tickers[: cfg["universe"]["max_tickers"]]

    # 2. Prices (batched) -> price factors for whole universe
    close, vol = data.get_price_matrix(
        tickers, period=cfg["prices"]["period"], chunk_size=cfg["prices"]["chunk_size"]
    )
    pf = factors.price_factors(close, vol)
    pf = factors.apply_universe_filter(
        pf, cfg["universe"]["min_price"], cfg["universe"]["min_dollar_volume"]
    )

    # 3. Layer-2 momentum gate -> survivors
    survivors = factors.apply_momentum_gate(pf, cfg["screen"])
    print(f"[pipeline] {len(survivors)} survivors enter fundamental fetch")

    # 4. Fundamentals only on survivors (slow path, bounded set)
    rows = [data.get_fundamentals(t) for t in survivors.index]
    fund = factors.fundamental_factors(rows) if rows else pd.DataFrame()

    # 5. Composite score + rank
    ranked = scoring.composite_score(survivors, fund, cfg["factors"]["weights"])
    return ranked


def main():
    cfg = load_config(os.environ.get("CONFIG", "config.yaml"))
    regime_ok = check_regime(cfg)
    ranked = run(cfg)
    top_n = cfg["report"]["top_n"]
    html = email_report.build_html(ranked, top_n, regime_ok)

    if os.environ.get("DRY_RUN") == "1":
        cols = ["score", "rs_rank", "momentum", "growth_raw", "quality_raw", "sector"]
        print(ranked.head(top_n)[[c for c in cols if c in ranked.columns]].to_string())
    else:
        email_report.send_email(html)


if __name__ == "__main__":
    main()
