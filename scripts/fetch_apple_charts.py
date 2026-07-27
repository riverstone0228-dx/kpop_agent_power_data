"""
Apple Music の公式RSSフィードから日本(jp)・韓国(kr)・米国(us)のトップソングチャートを取得する。

- 認証不要・完全無料・公式提供のためスクレイピング不要
- 各曲の genres に {"genreId":"51","name":"K-Pop"} が含まれるかでK-pop判定
- artist_master.csv / other_agency_master.csv の apple_artist_id と突合し、
  4大事務所およびOTHERのアーティストを識別する
  (韓国版はアーティスト名が韓国語表記になるため、名前ではなくIDで名寄せする)

出力:
  data/apple_charts/YYYY-MM-DD.csv      … 全チャートの生データ (国×順位×曲)
  data/apple_charts/summary_YYYY-MM-DD.csv … 国×事務所の集計 (ランクイン曲数)

実行:
  python fetch_apple_charts.py
  python fetch_apple_charts.py --limit 200   # 取得件数を変更 (デフォルト100)
"""

import csv
import os
import sys
import datetime
import argparse
import requests

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "apple_charts")

COUNTRIES = ["jp", "kr", "us"]
KPOP_GENRE_ID = "51"

RSS_URL = (
    "https://rss.marketingtools.apple.com/api/v2/{country}"
    "/music/most-played/{limit}/songs.json"
)

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)"
}


def apple_artwork_larger(url: str) -> str:
    """レポート用に 100px → 300px。"""
    url = (url or "").strip()
    if not url:
        return ""
    return url.replace("100x100bb", "300x300bb").replace("/100x100", "/300x300")


def fetch_chart(country, limit):
    """1カ国分のチャートを取得。戻り値: (updated, results)"""
    url = RSS_URL.format(country=country, limit=limit)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    feed = resp.json().get("feed", {})
    return feed.get("updated", ""), feed.get("results", [])


def is_kpop(entry):
    return any(g.get("genreId") == KPOP_GENRE_ID for g in entry.get("genres", []))


def build_artist_lookup():
    """apple_artist_id -> マスタ行 の辞書を作る。"""
    lookup = {}
    for row in load_all_artists():
        aid = (row.get("apple_artist_id") or "").strip()
        if aid:
            lookup[aid] = row
    return lookup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="取得件数 (10/25/50/100/200)")
    args = parser.parse_args()

    today = datetime.date.today().isoformat()
    artist_lookup = build_artist_lookup()
    if not artist_lookup:
        print("[WARN] apple_artist_id が1件も設定されていません。")
        print("       resolve_apple_artist_ids.py を実行してマスタを埋めてください。")
        print("       (チャート生データの取得は続行します)")

    all_rows = []

    for country in COUNTRIES:
        try:
            updated, results = fetch_chart(country, args.limit)
        except Exception as e:
            print(f"[WARN] {country} のチャート取得に失敗: {e}")
            continue

        print(f"{country}: {len(results)}件取得 (feed updated: {updated})")

        for rank, entry in enumerate(results, start=1):
            apple_artist_id = entry.get("artistId", "")
            master = artist_lookup.get(apple_artist_id)

            all_rows.append(
                {
                    "date": today,
                    "feed_updated": updated,
                    "country": country,
                    "rank": rank,
                    "track_name": entry.get("name", ""),
                    "artist_name_local": entry.get("artistName", ""),
                    "apple_artist_id": apple_artist_id,
                    "apple_track_id": entry.get("id", ""),
                    "release_date": entry.get("releaseDate", ""),
                    "artwork_url": apple_artwork_larger(entry.get("artworkUrl100", "")),
                    "is_kpop_genre": "1" if is_kpop(entry) else "0",
                    # マスタに載っているアーティストなら事務所情報を付与
                    "agency": master["agency"] if master else "",
                    "sub_agency": master.get("sub_agency", "") if master else "",
                    "artist_name_master": master["artist_name_en"] if master else "",
                }
            )

    if not all_rows:
        print("チャートを1件も取得できませんでした。処理を中止します。")
        return

    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 生データ ---
    raw_path = os.path.join(OUT_DIR, f"{today}.csv")
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n生データ: {raw_path} ({len(all_rows)}行)")

    # --- 集計: 国 × 事務所 のランクイン曲数 ---
    summary = {}
    for r in all_rows:
        country = r["country"]
        # マスタに載っていればその事務所、載っていないK-pop曲は"(その他K-pop)"
        if r["agency"]:
            agency = r["agency"]
        elif r["is_kpop_genre"] == "1":
            agency = "(未登録K-pop)"
        else:
            continue  # K-popでもマスタ掲載でもない曲は集計対象外
        key = (country, agency)
        summary[key] = summary.get(key, 0) + 1

    total_by_country = {}
    for r in all_rows:
        total_by_country[r["country"]] = total_by_country.get(r["country"], 0) + 1

    summary_path = os.path.join(OUT_DIR, f"summary_{today}.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "country", "agency", "charted_tracks", "chart_size", "share_pct"])
        for (country, agency), count in sorted(summary.items()):
            total = total_by_country.get(country, 0)
            share = round(count / total * 100, 1) if total else 0
            w.writerow([today, country, agency, count, total, share])
    print(f"集計:   {summary_path}")

    # --- コンソールに要約を表示 ---
    print("\n--- 国別 K-popランクイン状況 ---")
    for country in COUNTRIES:
        kpop_count = sum(
            1 for r in all_rows if r["country"] == country and r["is_kpop_genre"] == "1"
        )
        total = total_by_country.get(country, 0)
        if total:
            print(f"{country}: TOP{total}中 K-pop {kpop_count}曲 ({kpop_count/total*100:.1f}%)")


if __name__ == "__main__":
    main()
