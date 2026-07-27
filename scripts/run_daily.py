"""
日次収集オーケストレータ。

1. YouTube / Wikipedia → data/raw/YYYY-MM-DD.csv
2. Apple Music チャート (jp/kr/us)
3. LINE MUSIC K-Pop Top 50 (日次)
4. スペースシャワー KOREAN HITS (週次)
5. チャートから外部ID採掘 → OTHER TOP15 リバランス

GitHub Actionsの日次cronから呼び出される想定。
1ソースが失敗しても他は継続する。

データソース方針: YouTube / Wikipedia / Apple / LINE / Space Shower。
Spotifyは2026年2月のAPI変更により不使用 (spotify-api-change-2026.md)。
"""

import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from fetch_youtube import fetch_all as fetch_youtube_all
from fetch_wikipedia import get_pageviews
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def safe_call(label, func, *args, **kwargs):
    """1つのソースがエラーでも他は止めない。"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[WARN] {label} の取得に失敗しました: {e}")
        return None


def collect_artist_snapshots():
    rows = load_all_artists()
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    yt_results = safe_call("YouTube", fetch_youtube_all) or []
    yt_by_key = {(r["agency"], r["artist_name"]): r for r in yt_results}

    merged = []
    for row in rows:
        key = (row["agency"], row["artist_name_en"])
        yt = yt_by_key.get(key, {})

        pv_ja = safe_call(
            f"Wikipedia(ja) {row['artist_name_en']}",
            get_pageviews,
            row.get("wikipedia_title_ja", ""),
            "ja",
            yesterday,
        )
        pv_en = safe_call(
            f"Wikipedia(en) {row['artist_name_en']}",
            get_pageviews,
            row.get("wikipedia_title_en", ""),
            "en",
            yesterday,
        )

        merged.append(
            {
                "date": today.isoformat(),
                "agency": row["agency"],
                "sub_agency": row.get("sub_agency", ""),
                "artist_name": row["artist_name_en"],
                "youtube_subscribers": yt.get("youtube_subscribers", ""),
                "youtube_total_views": yt.get("youtube_total_views", ""),
                "youtube_video_count": yt.get("youtube_video_count", ""),
                "wikipedia_pv_ja": pv_ja if pv_ja is not None else "",
                "wikipedia_pv_en": pv_en if pv_en is not None else "",
            }
        )

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{today.isoformat()}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(merged[0].keys()))
        writer.writeheader()
        writer.writerows(merged)

    print(f"\n{len(merged)}件を {out_path} に保存しました。")


def collect_charts():
    from fetch_apple_charts import main as fetch_apple_main
    from fetch_line_charts import main as fetch_line_main
    from fetch_spaceshower_charts import main as fetch_sstv_main
    from mine_chart_ids import main as mine_ids_main

    print("\n=== Apple Music charts ===")
    safe_call("Apple charts", fetch_apple_main)

    print("\n=== LINE MUSIC charts ===")
    safe_call("LINE MUSIC charts", fetch_line_main)

    print("\n=== Space Shower charts (weekly) ===")
    safe_call("Space Shower charts", fetch_sstv_main)

    print("\n=== Mine chart external IDs ===")
    safe_call("mine_chart_ids", mine_ids_main)

    print("\n=== Re-enrich LINE / Space Shower with updated ID map ===")
    safe_call("LINE MUSIC charts (re-enrich)", fetch_line_main)
    safe_call("Space Shower charts (re-enrich)", fetch_sstv_main)

    print("\n=== OTHER TOP15 rebalance ===")
    from rank_other_agency_top15 import main as rank_other_main

    safe_call("OTHER TOP15", rank_other_main)


def main():
    print("=== Artist daily snapshots ===")
    safe_call("artist snapshots", collect_artist_snapshots)

    collect_charts()
    print("\n日次収集完了。")


if __name__ == "__main__":
    main()
