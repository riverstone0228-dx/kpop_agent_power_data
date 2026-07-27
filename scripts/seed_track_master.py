"""
track_master.csv の初期候補を自動生成する。

選定ロジック:
  1. アーティストごとのYouTube累積再生数TOP10動画 (公式ch内、search.list(order=viewCount))
  2. チャートに出現した楽曲 (Apple / LINE / スペースシャワー の track_external_ids
     および直近チャートCSVで master 突合できた曲)

方針: 自動で track_master.csv を確定上書きはしない。
  track_candidates_report.csv に選定理由付きで出力するので、
  重複除去・track_type判定 (title/b-side等) は人が見て track_master.csv に確定する。

注意:
  - YouTube search.list は1回100ユニット。アーティスト数が多いと消費が大きいので、
    このスクリプトは「一括ブートストラップ用」であり、毎日実行する想定ではない。

実行前準備:
  pip install -r requirements.txt
  .env に YOUTUBE_API_KEY を設定

実行:
  python seed_track_master.py
  → track_candidates_report.csv が生成される
"""

import csv
import glob
import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

load_dotenv()

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
REPORT_CSV = os.path.join(os.path.dirname(__file__), "track_candidates_report.csv")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def get_youtube_top_videos(channel_id, api_key, max_results=10):
    """公式ch内で再生数順TOP10。search.listは100ユニット/回なので多用しないこと。"""
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
            "key": api_key,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return []
    items = resp.json().get("items", [])
    return [
        {
            "track_name": it["snippet"]["title"],
            "youtube_video_id": it["id"]["videoId"],
            "release_date": it["snippet"]["publishedAt"][:10],
        }
        for it in items
    ]


def chart_tracks_for_artists(artist_names):
    """直近チャートCSVから master 突合済みの曲を拾う。"""
    sources = [
        ("apple_chart", os.path.join(DATA_DIR, "apple_charts"), "artist_name_master", "track_name"),
        ("line_chart", os.path.join(DATA_DIR, "line_charts"), "artist_name_master", "track_name"),
        (
            "spaceshower_chart",
            os.path.join(DATA_DIR, "spaceshower_charts"),
            "artist_name_master",
            "track_name",
        ),
    ]
    found = []
    seen = set()
    for reason, directory, artist_col, track_col in sources:
        paths = sorted(
            [
                p
                for p in glob.glob(os.path.join(directory, "[0-9]*.csv"))
                if not os.path.basename(p).startswith("summary_")
            ]
        )[-3:]  # 直近最大3ファイル
        for path in paths:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = (row.get(artist_col) or "").strip()
                    track = (row.get(track_col) or "").strip()
                    if name not in artist_names or not track:
                        continue
                    key = (name, track, reason)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        {
                            "artist_name_en": name,
                            "track_name": track,
                            "selection_reason": reason,
                        }
                    )
    return found


def main():
    artists = [
        r
        for r in load_all_artists()
        if r["artist_name_en"].strip() and not r["artist_name_en"].startswith("(")
    ]
    by_name = {a["artist_name_en"].strip(): a for a in artists}
    candidates = []

    for artist in artists:
        name = artist["artist_name_en"].strip()
        yt_id = artist.get("youtube_channel_id", "").strip()

        if yt_id and YOUTUBE_API_KEY:
            for v in get_youtube_top_videos(yt_id, YOUTUBE_API_KEY):
                candidates.append(
                    {
                        "agency": artist["agency"],
                        "sub_agency": artist.get("sub_agency", ""),
                        "artist_name_en": name,
                        "track_name": v["track_name"],
                        "release_date": v["release_date"],
                        "youtube_video_id": v["youtube_video_id"],
                        "selection_reason": "youtube_top10",
                    }
                )
        else:
            print(f"[SKIP] {name}: youtube_channel_id未設定またはAPIキーなし")

    for t in chart_tracks_for_artists(set(by_name.keys())):
        artist = by_name[t["artist_name_en"]]
        candidates.append(
            {
                "agency": artist["agency"],
                "sub_agency": artist.get("sub_agency", ""),
                "artist_name_en": t["artist_name_en"],
                "track_name": t["track_name"],
                "release_date": "",
                "youtube_video_id": "",
                "selection_reason": t["selection_reason"],
            }
        )

    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "agency",
                "sub_agency",
                "artist_name_en",
                "track_name",
                "release_date",
                "youtube_video_id",
                "selection_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(candidates)

    print(f"\n{len(candidates)}件の候補を {REPORT_CSV} に出力しました。")
    print("重複除去・track_type判定をした上で track_master.csv に手動で確定してください。")


if __name__ == "__main__":
    main()
