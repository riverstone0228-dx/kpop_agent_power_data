"""
YouTube Data API v3 から登録者数・総再生数・動画数を取得する。
channels.list は1コール=1ユニットなので、最大50件までidをまとめて1回で取得可能。
"""

import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def get_channel_stats(channel_ids):
    """channel_ids: list[str] (最大50件)。戻り値: {channel_id: {...}}"""
    if not channel_ids:
        return {}
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "statistics,snippet",
            "id": ",".join(channel_ids),
            "key": YOUTUBE_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    out = {}
    for item in resp.json().get("items", []):
        stats = item["statistics"]
        out[item["id"]] = {
            "title": item["snippet"]["title"],
            "subscriber_count": stats.get("subscriberCount"),
            "view_count": stats.get("viewCount"),
            "video_count": stats.get("videoCount"),
            # レポート用: 小さいサムネで十分
            "thumbnail_url": (item["snippet"].get("thumbnails") or {})
            .get("default", {})
            .get("url", ""),
        }
    return out


def fetch_all():
    rows = load_all_artists()

    ids = [r["youtube_channel_id"].strip() for r in rows if r["youtube_channel_id"].strip()]
    missing = [r["artist_name_en"] for r in rows if not r["youtube_channel_id"].strip()]

    stats_by_id = {}
    # 50件ずつバッチ処理
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        stats_by_id.update(get_channel_stats(batch))

    results = []
    today = datetime.date.today().isoformat()
    for row in rows:
        cid = row["youtube_channel_id"].strip()
        stat = stats_by_id.get(cid, {})
        results.append(
            {
                "date": today,
                "agency": row["agency"],
                "artist_name": row["artist_name_en"],
                "youtube_channel_id": cid,
                "youtube_subscribers": stat.get("subscriber_count", ""),
                "youtube_total_views": stat.get("view_count", ""),
                "youtube_video_count": stat.get("video_count", ""),
                "youtube_channel_thumbnail": stat.get("thumbnail_url", ""),
            }
        )

    if missing:
        print(f"channel_id未設定のためスキップ ({len(missing)}件): {', '.join(missing)}")

    return results


if __name__ == "__main__":
    for r in fetch_all():
        print(r)
