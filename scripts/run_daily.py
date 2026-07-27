"""
日次収集オーケストレータ。

1. YouTube / Wikipedia → data/raw/YYYY-MM-DD.csv
2. YouTube 動画 (直近10 + 再生TOP10) → data/youtube_videos/
3. 4大事務所株価 (HYBE/JYP/YG/SM) → data/stock_prices/
4. Apple Music チャート (jp/kr/us)
5. LINE MUSIC K-Pop Top 50 (日次)
6. スペースシャワー KOREAN HITS (週次)
7. チャートから外部ID採掘 → track_master 更新 → TOP/HOT SONG20 → OTHER TOP15
8. Slack に収集サマリーを通知

GitHub Actionsの日次cronから呼び出される想定。
1ソースが失敗しても他は継続する。

データソース方針: YouTube / Wikipedia / Apple / LINE / Space Shower / 株価。
Spotifyは2026年2月のAPI変更により不使用 (spotify-api-change-2026.md)。
"""

import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fetch_youtube import fetch_all as fetch_youtube_all
from fetch_wikipedia import get_pageviews
from master_data import load_all_artists
from notify_slack import CollectionReport, notify_collection

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# 実行全体で共有するレポート
REPORT = CollectionReport()


def safe_call(label, func, *args, report_step: bool = True, **kwargs):
    """1つのソースがエラーでも他は止めない。"""
    try:
        result = func(*args, **kwargs)
        if report_step:
            REPORT.mark_ok(label)
        return result
    except Exception as e:
        print(f"[WARN] {label} の取得に失敗しました: {e}")
        if report_step:
            REPORT.mark_fail(label, e)
        else:
            REPORT.warn(f"{label}: {e}")
        return None


def collect_artist_snapshots():
    rows = load_all_artists()
    today = datetime.date.today()
    # Pageviews API は直近1〜2日分が未公開のことが多いため一昨日を取る
    yesterday = today - datetime.timedelta(days=2)

    if not os.environ.get("YOUTUBE_API_KEY", "").strip():
        REPORT.warn("YOUTUBE_API_KEY 未設定 — YouTube列は空になります")

    yt_results = safe_call("YouTube", fetch_youtube_all) or []
    yt_by_key = {(r["agency"], r["artist_name"]): r for r in yt_results}

    wiki_errors = 0
    wiki_missing = 0
    merged = []
    for row in rows:
        key = (row["agency"], row["artist_name_en"])
        yt = yt_by_key.get(key, {})

        pv_ja = None
        pv_en = None
        title_ja = row.get("wikipedia_title_ja", "")
        title_en = row.get("wikipedia_title_en", "")
        try:
            pv_ja = get_pageviews(title_ja, "ja", yesterday)
            if title_ja and pv_ja is None:
                wiki_missing += 1
        except Exception as e:
            wiki_errors += 1
            REPORT.warn(f"Wikipedia(ja) {row['artist_name_en']}: {e}")

        try:
            pv_en = get_pageviews(title_en, "en", yesterday)
            if title_en and pv_en is None:
                wiki_missing += 1
        except Exception as e:
            wiki_errors += 1
            REPORT.warn(f"Wikipedia(en) {row['artist_name_en']}: {e}")

        merged.append(
            {
                "date": today.isoformat(),
                "agency": row["agency"],
                "sub_agency": row.get("sub_agency", ""),
                "artist_name": row["artist_name_en"],
                "youtube_subscribers": yt.get("youtube_subscribers", ""),
                "youtube_total_views": yt.get("youtube_total_views", ""),
                "youtube_video_count": yt.get("youtube_video_count", ""),
                "youtube_channel_thumbnail": yt.get("youtube_channel_thumbnail", ""),
                "wikipedia_pv_ja": pv_ja if pv_ja is not None else "",
                "wikipedia_pv_en": pv_en if pv_en is not None else "",
            }
        )

    if wiki_missing:
        REPORT.warn(f"Wikipedia 記事なし/PV無し: {wiki_missing}件")
    if wiki_errors:
        REPORT.mark_fail("Wikipedia", f"API例外 {wiki_errors}件")
    else:
        REPORT.mark_ok("Wikipedia")

    if not merged:
        raise RuntimeError("アーティストマスタが空のため snapshot を書けません")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{today.isoformat()}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(merged[0].keys()))
        writer.writeheader()
        writer.writerows(merged)

    print(f"\n{len(merged)}件を {out_path} に保存しました。")
    return len(merged)


def collect_youtube_videos():
    from fetch_youtube_videos import main as fetch_yt_videos_main

    print("\n=== YouTube videos (recent10 + top10 views) ===")
    safe_call("YouTube videos", fetch_yt_videos_main)


def collect_stock_prices():
    from fetch_stock_prices import main as fetch_stock_main

    print("\n=== Agency stock prices (HYBE/JYP/YG/SM) ===")
    safe_call("stock prices", fetch_stock_main)


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

    print("\n=== Build track master ===")
    from build_track_master import main as build_track_main

    safe_call("build_track_master", build_track_main)

    print("\n=== Enrich media URLs (logos / thumbs / artwork) ===")
    from enrich_media_assets import main as enrich_media_main

    safe_call("enrich_media_assets", enrich_media_main)

    print("\n=== TOP / HOT SONG 20 ===")
    from rank_songs import main as rank_songs_main

    safe_call("song rankings", rank_songs_main)

    print("\n=== GitHub Pages report ===")
    from build_report import main as build_report_main

    safe_call("build_report", build_report_main)

    print("\n=== OTHER TOP15 rebalance ===")
    from rank_other_agency_top15 import main as rank_other_main

    safe_call("OTHER TOP15", rank_other_main)


def main():
    try:
        print("=== Artist daily snapshots ===")
        safe_call("artist snapshots", collect_artist_snapshots)

        collect_youtube_videos()
        collect_stock_prices()
        collect_charts()
        print("\n日次収集完了。")
    finally:
        try:
            notify_collection(REPORT)
        except Exception as e:
            print(f"[WARN] Slack通知処理で例外: {e}")


if __name__ == "__main__":
    main()
