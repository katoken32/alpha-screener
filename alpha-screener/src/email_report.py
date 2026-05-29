"""Email the ranked watchlist via Gmail SMTP.

Credentials come from environment (set as GitHub Secrets):
  GMAIL_USER             -> your gmail address (also the From)
  GMAIL_APP_PASSWORD     -> a 16-char Google App Password (NOT your login pw)
  REPORT_TO              -> recipient (defaults to GMAIL_USER)

App Password requires 2-Step Verification enabled on the Google account.
"""
from __future__ import annotations
import os
import smtplib
import datetime as dt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd

COLS = ["score", "rs_rank", "momentum", "dist_high", "vol_surge",
        "growth_raw", "quality_raw", "sector"]


def _fmt(df: pd.DataFrame) -> str:
    d = df.copy()
    for c in ["momentum", "dist_high", "growth_raw", "quality_raw"]:
        if c in d:
            d[c] = (d[c] * 100).round(1).astype(str) + "%"
    for c in ["score", "rs_rank", "vol_surge"]:
        if c in d:
            d[c] = d[c].round(2)
    keep = [c for c in COLS if c in d.columns]
    return d[keep].to_html(border=0, justify="center")


def build_html(ranked: pd.DataFrame, top_n: int, regime_ok: bool) -> str:
    today = dt.date.today().isoformat()
    flag = ("📈 市場は上昇レジーム（200日線上）。新規エントリー検討可。"
            if regime_ok else
            "⚠️ 市場は防御レジーム（指数が200日線下）。監視のみ推奨。")
    table = _fmt(ranked.head(top_n))
    return f"""
    <html><body style="font-family:Arial,sans-serif;font-size:13px">
    <h2>Alpha Screener — {today}</h2>
    <p>{flag}</p>
    <p>Top {top_n} by composite score (momentum + trend + growth + quality).</p>
    {table}
    <p style="color:#888;font-size:11px">
    候補抽出であって売買シグナルではありません。自由データ由来のファンダは
    point-in-time非対応のため参考値です。投資判断は自己責任で。</p>
    </body></html>
    """


def send_email(html: str, subject: str | None = None) -> None:
    user = os.environ["GMAIL_USER"]
    pw = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("REPORT_TO", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject or f"Alpha Screener — {dt.date.today().isoformat()}"
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"[email] sent to {to}")
