"""Publish top-N screener candidates to a JSON file for downstream consumers.

下流（alpha_notifier のウォッチリスト）が raw.githubusercontent.com 経由で
取得できるよう、上位候補を output/latest_candidates.json に書き出す。
CIワークフローがこのファイルをリポジトリにコミットする。

原則: これは「候補抽出」であって売買シグナルではない。
      下流は監視（ウォッチリスト）用途のみに使い、発注は人間が判断する。
"""
from __future__ import annotations
import json
import os
import datetime as dt
import pandas as pd


def write_candidates(ranked: pd.DataFrame, n: int,
                     path: str = "output/latest_candidates.json") -> str:
    """composite_score 済みの ranked（ティッカーをindexに持つ想定）から
    上位 n 件を JSON に書き出す。"""
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    top = ranked.head(n)
    candidates = []
    for rank, (tk, row) in enumerate(top.iterrows(), 1):
        score = row.get("score") if hasattr(row, "get") else None
        candidates.append({
            "ticker": str(tk).upper().strip(),
            "rank": rank,
            "score": (round(float(score), 4)
                      if score is not None and pd.notna(score) else None),
        })

    payload = {
        "date": dt.date.today().isoformat(),
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "source": "alpha-screener",
        "count": len(candidates),
        "candidates": candidates,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[publish] wrote {len(candidates)} candidates -> {path}")
    return path
