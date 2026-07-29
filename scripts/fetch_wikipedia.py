"""
Wikipedia Pageviews API からページビュー数を取得する。
認証不要・完全無料。artist_master.csv の wikipedia_title_ja / wikipedia_title_en を使う。

方針（レート制限対策）:
  - 日次ではなく **週1回**（既定: 月曜）に、直近7日合計を取得
  - 1記事×1言語につき **1リクエスト**（日付レンジ指定）で7日分を合計
  - リクエスト間に待機。429 時はリトライ

実行:
  python fetch_wikipedia.py              # 月曜でなければスキップ（--force で強制）
  python fetch_wikipedia.py --force
  python fetch_wikipedia.py --end 2026-07-25
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

HEADERS = {
    # Wikimedia: 識別可能な User-Agent（連絡先付き）が必須
    "User-Agent": "riverstone-kpop-power-index/0.2 (https://github.com/riverstone0228-dx/kpop_agent_power_data; riverstone0228@gmail.com)"
}

# 月曜=0 … 日曜=6。この曜日だけ週次取得する
WIKI_WEEKDAY = 0
REQUEST_SLEEP_SEC = 0.6
MAX_RETRIES = 4


def get_pageviews_sum(title: str, lang: str, start: datetime.date, end: datetime.date):
    """日付レンジの日次PVを1リクエストで取得し合計。記事なしは None。"""
    if not title:
        return None
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia/all-access/all-agents/{encoded}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )

    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            wait = REQUEST_SLEEP_SEC * (2 ** attempt)
            print(f"[WARN] 429 rate limit ({lang}:{title}) — sleep {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None
        return sum(int(i.get("views") or 0) for i in items)

    raise RuntimeError(f"Wikipedia rate limit persisted: {lang}:{title}")


# 後方互換: 1日分
def get_pageviews(title, lang, date):
    return get_pageviews_sum(title, lang, date, date)


def should_run_weekly(today: datetime.date, force: bool) -> bool:
    if force or os.environ.get("WIKIPEDIA_FORCE", "").strip() in ("1", "true", "TRUE"):
        return True
    return today.weekday() == WIKI_WEEKDAY


def fetch_all_weekly(end: datetime.date, days: int = 7):
    start = end - datetime.timedelta(days=days - 1)
    rows = load_all_artists()
    results = []
    not_found = []

    print(f"Wikipedia 7日合計: {start.isoformat()} ～ {end.isoformat()} ({len(rows)} artists)")

    for row in rows:
        name = row["artist_name_en"]
        title_ja = (row.get("wikipedia_title_ja") or "").strip()
        title_en = (row.get("wikipedia_title_en") or "").strip()

        pv_ja = get_pageviews_sum(title_ja, "ja", start, end) if title_ja else None
        time.sleep(REQUEST_SLEEP_SEC)
        pv_en = get_pageviews_sum(title_en, "en", start, end) if title_en else None
        time.sleep(REQUEST_SLEEP_SEC)

        if title_ja and pv_ja is None:
            not_found.append(f"{name} (ja: {title_ja})")
        if title_en and pv_en is None:
            not_found.append(f"{name} (en: {title_en})")

        results.append(
            {
                "date": end.isoformat(),  # 集計終端日（スナップショット紐付け用）
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "agency": row["agency"],
                "artist_name": name,
                "wikipedia_pv_ja": pv_ja if pv_ja is not None else "",
                "wikipedia_pv_en": pv_en if pv_en is not None else "",
            }
        )
        print(f"{name}: ja_7d={pv_ja} en_7d={pv_en}")

    return results, not_found, start, end


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="曜日に関係なく実行")
    parser.add_argument("--end", help="集計終端日 YYYY-MM-DD（既定: 今日-2）")
    parser.add_argument("--days", type=int, default=7, help="合計する日数（既定7）")
    args = parser.parse_args(argv)

    today = datetime.date.today()
    if not should_run_weekly(today, args.force):
        print(
            f"Wikipedia は週次のみ（曜日={WIKI_WEEKDAY}=月曜）。"
            f"今日は weekday={today.weekday()} のためスキップ。--force で強制可。"
        )
        return None

    end = (
        datetime.datetime.strptime(args.end, "%Y-%m-%d").date()
        if args.end
        else today - datetime.timedelta(days=2)
    )

    results, not_found, start, end = fetch_all_weekly(end, days=args.days)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"wikipedia_7d_{end.isoformat()}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "period_start",
                "period_end",
                "agency",
                "artist_name",
                "wikipedia_pv_ja",
                "wikipedia_pv_en",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\n保存先: {out_path}")
    if not_found:
        print(f"\n記事が見つからない項目 ({len(not_found)}件):")
        for item in not_found:
            print(f"  - {item}")
    return results


if __name__ == "__main__":
    main()
