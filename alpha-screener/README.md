# Alpha Screener (free-data MVP)

毎朝、米国全体の株式から多因子スコア上位を抽出し、Gmail でメール配信する
GitHub Actions パイプライン。設計は「テーマ/モメンタムで安く広く絞り、
ファンダは通過銘柄だけに高コストで取りに行く」ファネル方式。

## 何をするか（ファネル）

1. **Universe** — NASDAQ Trader の公開シンボルから米国上場の普通株を構築
2. **Price factors（全銘柄・一括DL）** — モメンタム(6M/12-1)、RSランク、52週高値乖離、出来高サージ、トレンド構造
3. **Layer-2 gate** — RSランク上位・高値圏・上昇トレンドの銘柄だけ通過
4. **Fundamentals（通過銘柄のみ）** — 売上成長/加速、EPS成長、粗利率（yfinance）
5. **Composite score** — 各因子を頑健Zスコア化→加重合成→ランク
6. **Regime + Email** — 指数の200日線で地合いを判定し、上位Nを HTML メール送信

## セットアップ

### 1. Gmail アプリパスワード
Google アカウントで2段階認証を有効化 → アプリパスワードを発行（16桁）。
通常のログインパスワードではなくこれを使う。

### 2. GitHub Secrets（Settings → Secrets and variables → Actions）
| Secret | 内容 |
|---|---|
| `GMAIL_USER` | 送信元の Gmail アドレス |
| `GMAIL_APP_PASSWORD` | 上で発行した16桁 |
| `REPORT_TO` | 受信先（省略時は GMAIL_USER） |

### 3. 配信スケジュール
`.github/workflows/daily.yml` の cron を編集（**UTC**）。既定は平日 11:30 UTC。

## ローカル実行

```bash
pip install -r requirements.txt
DRY_RUN=1 python -m src.pipeline          # メール送らず上位を表示
python -m src.pipeline                     # 実際に送信（env必要）
python tests/test_factors.py               # オフライン検証
```

> 初回フルランは米国全体スキャンのため十数分かかることがあります。動作確認は
> `config.yaml` の `universe.max_tickers` を 500 等に設定すると速いです。

## 係数の最適化（バックテスト）

```bash
python -m src.backtest --tickers AAPL MSFT NVDA MU ARM AVGO MRVL ...
```

月次ウォークフォワードで IC（情報係数）と上位/下位5分位スプレッドを計算し、
モメンタム×トレンドの重みをグリッド探索。良い重みを `config.yaml` に転記する。

## 正直な制約（重要）

- **無料データは予想修正（Zacks Rank相当）を出せない** → 当初設計の revision 因子は
  本MVPで除外し、重みをモメンタム/成長に再配分済み。
- **バックテストは価格因子のみ厳密**。ファンダは point-in-time 非対応のため、検証に
  使うと先読み＋生存バイアスで「綺麗なゴミ」になる。だから backtest は価格因子に限定。
- **yfinance は非公式**。欠損・一時失敗は前提で、該当銘柄をスキップして継続する設計。
- これは**候補抽出**であって売買シグナルではない。執行・リスク管理（レイヤー5）は別途。

## アップグレード経路（有料データ）

- `src/data.py` の `get_fundamentals` を FMP / Finnhub に差し替え → 予想修正因子を復活
- point-in-time 履歴（Sharadar 等）→ ファンダ因子もバックテスト可能に
- スコア重みを4因子フルで最適化

## 構成

```
config.yaml                 # 閾値・重み・ユニバース条件
src/universe.py             # 米国ユニバース構築
src/data.py                 # 価格一括DL + 個別ファンダ
src/factors.py              # 価格因子 / ゲート / ファンダ因子
src/scoring.py              # Zスコア・加重合成・ランク
src/backtest.py             # IC / 分位 / 重みグリッド
src/email_report.py         # HTML生成 + Gmail送信
src/pipeline.py             # 朝の本番オーケストレーション
.github/workflows/daily.yml # cron トリガー
tests/test_factors.py       # オフライン検証
```
