"""
4大事務所の韓国株価を日次取得する。

HYBE  352820.KS  (KOSPI / KRX)
JYP   035900.KQ  (KOSDAQ)
YG    122870.KQ  (KOSDAQ)
SM    041510.KQ  (KOSDAQ)

Yahoo Finance Chart API（認証不要）。休場日は直近取引日の終値を返す。

出力:
  data/stock_prices/YYYY-MM-DD.csv

実行:
  python fetch_stock_prices.py
"""

from __future__ import annotations

import csv
import datetime
import os
import sys

import requests

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "stock_prices")

# agency は既存マスタ表記に合わせる
AGENCIES = [
    {
        "agency": "HYBE",
        "ticker": "352820",
        "yahoo_symbol": "352820.KS",
        "market": "KRX",
        "exchange": "KOSPI",
    },
    {
        "agency": "JYP",
        "ticker": "035900",
        "yahoo_symbol": "035900.KQ",
        "market": "KOSDAQ",
        "exchange": "KOSDAQ",
    },
    {
        "agency": "YG",
        "ticker": "122870",
        "yahoo_symbol": "122870.KQ",
        "market": "KOSDAQ",
        "exchange": "KOSDAQ",
    },
    {
        "agency": "SM",
        "ticker": "041510",
        "yahoo_symbol": "041510.KQ",
        "market": "KOSDAQ",
        "exchange": "KOSDAQ",
    },
]

CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?interval=1d&range=10d"
)

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)"
}

FIELDNAMES = [
    "date",
    "trade_date",
    "agency",
    "ticker",
    "market",
    "exchange",
    "yahoo_symbol",
    "currency",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


def fetch_quote(symbol: str) -> dict:
    url = CHART_URL.format(symbol=symbol)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    err = (payload.get("chart") or {}).get("error")
    if err:
        raise RuntimeError(f"Yahoo chart error for {symbol}: {err}")
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo chart empty for {symbol}")

    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]

    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []

    # 末尾から有効な終値バーを探す（休場・欠損対策）
    idx = None
    for i in range(len(closes) - 1, -1, -1):
        if closes[i] is not None and i < len(timestamps):
            idx = i
            break
    if idx is None:
        # fallback: meta の現値のみ
        price = meta.get("regularMarketPrice")
        if price is None:
            raise RuntimeError(f"No price bars for {symbol}")
        trade_date = datetime.date.today().isoformat()
        return {
            "trade_date": trade_date,
            "currency": meta.get("currency") or "KRW",
            "open": "",
            "high": "",
            "low": "",
            "close": float(price),
            "volume": "",
        }

    trade_date = datetime.datetime.utcfromtimestamp(timestamps[idx]).date().isoformat()
    return {
        "trade_date": trade_date,
        "currency": meta.get("currency") or "KRW",
        "open": opens[idx] if idx < len(opens) and opens[idx] is not None else "",
        "high": highs[idx] if idx < len(highs) and highs[idx] is not None else "",
        "low": lows[idx] if idx < len(lows) and lows[idx] is not None else "",
        "close": closes[idx],
        "volume": volumes[idx] if idx < len(volumes) and volumes[idx] is not None else "",
    }


def main():
    today = datetime.date.today().isoformat()
    rows = []
    errors = []

    for ag in AGENCIES:
        try:
            q = fetch_quote(ag["yahoo_symbol"])
            rows.append(
                {
                    "date": today,
                    "trade_date": q["trade_date"],
                    "agency": ag["agency"],
                    "ticker": ag["ticker"],
                    "market": ag["market"],
                    "exchange": ag["exchange"],
                    "yahoo_symbol": ag["yahoo_symbol"],
                    "currency": q["currency"],
                    "open": q["open"],
                    "high": q["high"],
                    "low": q["low"],
                    "close": q["close"],
                    "volume": q["volume"],
                }
            )
            print(
                f"{ag['agency']}: close={q['close']} ({q['currency']}) "
                f"trade_date={q['trade_date']}"
            )
        except Exception as e:
            errors.append(f"{ag['agency']}: {e}")
            print(f"[WARN] {ag['agency']} 取得失敗: {e}", file=sys.stderr)

    if not rows:
        raise RuntimeError("株価を1件も取得できませんでした: " + "; ".join(errors))

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{today}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(rows)}件を {out_path} に保存しました。")
    if errors:
        print(f"[WARN] 一部失敗: {errors}", file=sys.stderr)
    return len(rows)


if __name__ == "__main__":
    main()
