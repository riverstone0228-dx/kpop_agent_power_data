"""
公式チャンネルから動画単位の再生・いいね・コメントを取得する。

取得対象 (アーティストごと):
  1. リリース直近10本 … uploads プレイリスト (playlistItems.list)
  2. 累積再生数 TOP10 … search.list(order=viewCount)

各動画は videos.list で title / url / views / likes / comments を付与。

注意:
  - search.list は 100 ユニット/回。アーティスト数×1 で日次枠を大きく消費する。
  - 「公式MV」厳密フィルタはしない (タイトルに M/V 等が無い動画も含む)。
  - likeCount / commentCount は投稿者設定で非公開の場合がある。

出力:
  data/youtube_videos/YYYY-MM-DD.csv

実行:
  python fetch_youtube_videos.py
"""

from __future__ import annotations

import csv
import datetime
import os
import sys
import time

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "youtube_videos")
API = "https://www.googleapis.com/youtube/v3"


def _get(path, params):
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY 未設定")
    params = {**params, "key": YOUTUBE_API_KEY}
    resp = requests.get(f"{API}/{path}", params=params, timeout=20)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube API {path} HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def get_uploads_playlist_ids(channel_ids: list[str]) -> dict[str, str]:
    """channel_id -> uploads playlist id"""
    out = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        data = _get(
            "channels",
            {"part": "contentDetails", "id": ",".join(batch)},
        )
        for item in data.get("items", []):
            uploads = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            if uploads:
                out[item["id"]] = uploads
        time.sleep(0.05)
    return out


def get_recent_video_ids(uploads_playlist_id: str, max_results: int = 10) -> list[dict]:
    """直近アップロード。戻り値: [{video_id, published_at, title_hint}]"""
    data = _get(
        "playlistItems",
        {
            "part": "contentDetails,snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": max_results,
        },
    )
    rows = []
    for it in data.get("items", []):
        vid = it.get("contentDetails", {}).get("videoId", "")
        if not vid:
            continue
        rows.append(
            {
                "video_id": vid,
                "published_at": (it.get("contentDetails", {}).get("videoPublishedAt") or "")[:10],
                "title_hint": it.get("snippet", {}).get("title", ""),
            }
        )
    return rows


def get_top_video_ids(channel_id: str, max_results: int = 10) -> list[dict]:
    """累積再生数順 TOP。search.list = 100 units。"""
    data = _get(
        "search",
        {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
        },
    )
    rows = []
    for it in data.get("items", []):
        vid = it.get("id", {}).get("videoId", "")
        if not vid:
            continue
        rows.append(
            {
                "video_id": vid,
                "published_at": (it.get("snippet", {}).get("publishedAt") or "")[:10],
                "title_hint": it.get("snippet", {}).get("title", ""),
            }
        )
    return rows


def get_video_stats(video_ids: list[str]) -> dict[str, dict]:
    """videos.list で statistics + snippet。最大50件/回。"""
    out = {}
    unique = list(dict.fromkeys(v for v in video_ids if v))
    for i in range(0, len(unique), 50):
        batch = unique[i : i + 50]
        data = _get(
            "videos",
            {"part": "snippet,statistics", "id": ",".join(batch)},
        )
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            st = item.get("statistics", {})
            out[item["id"]] = {
                "title": sn.get("title", ""),
                "published_at": (sn.get("publishedAt") or "")[:10],
                "view_count": st.get("viewCount", ""),
                "like_count": st.get("likeCount", ""),  # 非公開なら欠落
                "comment_count": st.get("commentCount", ""),
            }
        time.sleep(0.05)
    return out


def fetch_all(recent_n: int = 10, top_n: int = 10) -> list[dict]:
    artists = [
        r
        for r in load_all_artists()
        if r.get("youtube_channel_id", "").strip()
        and not r["artist_name_en"].startswith("(")
    ]
    channel_ids = [r["youtube_channel_id"].strip() for r in artists]
    uploads = get_uploads_playlist_ids(channel_ids)

    today = datetime.date.today().isoformat()
    pending: list[tuple] = []  # (row_meta without stats, video_id)

    for artist in artists:
        cid = artist["youtube_channel_id"].strip()
        name = artist["artist_name_en"]
        agency = artist["agency"]
        sub = artist.get("sub_agency", "")

        # 1) 直近
        pl = uploads.get(cid)
        recent = []
        if pl:
            try:
                recent = get_recent_video_ids(pl, recent_n)
            except Exception as e:
                print(f"[WARN] recent {name}: {e}")
        else:
            print(f"[WARN] uploads playlist なし: {name}")

        for rank, v in enumerate(recent, start=1):
            pending.append(
                (
                    {
                        "date": today,
                        "agency": agency,
                        "sub_agency": sub,
                        "artist_name": name,
                        "youtube_channel_id": cid,
                        "selection": "recent",
                        "rank": rank,
                        "video_id": v["video_id"],
                    },
                    v["video_id"],
                )
            )

        # 2) 再生 TOP
        try:
            top = get_top_video_ids(cid, top_n)
            time.sleep(0.1)
        except Exception as e:
            print(f"[WARN] top_views {name}: {e}")
            top = []

        for rank, v in enumerate(top, start=1):
            pending.append(
                (
                    {
                        "date": today,
                        "agency": agency,
                        "sub_agency": sub,
                        "artist_name": name,
                        "youtube_channel_id": cid,
                        "selection": "top_views",
                        "rank": rank,
                        "video_id": v["video_id"],
                    },
                    v["video_id"],
                )
            )

        print(f"{name}: recent={len(recent)} top={len(top)}")

    stats = get_video_stats([vid for _, vid in pending])
    rows = []
    for meta, vid in pending:
        st = stats.get(vid, {})
        rows.append(
            {
                **meta,
                "title": st.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published_at": st.get("published_at", ""),
                "view_count": st.get("view_count", ""),
                "like_count": st.get("like_count", ""),
                "comment_count": st.get("comment_count", ""),
            }
        )
    return rows


def main():
    rows = fetch_all()
    if not rows:
        print("取得0件。YOUTUBE_API_KEY / channel_id を確認してください。")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    out_path = os.path.join(OUT_DIR, f"{today}.csv")
    fieldnames = [
        "date",
        "agency",
        "sub_agency",
        "artist_name",
        "youtube_channel_id",
        "selection",
        "rank",
        "video_id",
        "title",
        "url",
        "published_at",
        "view_count",
        "like_count",
        "comment_count",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(rows)}件を {out_path} に保存しました。")


if __name__ == "__main__":
    main()
