"""
最新データから GitHub Pages 用レポート JSON を生成する。

出力:
  docs/data/report.json

実行:
  python build_report.py
"""

from __future__ import annotations

import csv
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

SCRIPTS = os.path.dirname(__file__)
ROOT = os.path.join(SCRIPTS, "..")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "docs", "data", "report.json")


def latest(directory, prefix=""):
    files = sorted(
        [
            p
            for p in glob.glob(os.path.join(directory, f"{prefix}*.csv"))
            if "summary" not in os.path.basename(p)
            and "changelog" not in os.path.basename(p)
        ]
    )
    return files[-1] if files else None


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def yt_thumb(video_id: str) -> str:
    vid = (video_id or "").strip()
    if not vid:
        return ""
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"


def load_artist_images():
    out = {}
    for name in ("artist_master.csv", "other_agency_master.csv"):
        path = os.path.join(SCRIPTS, name)
        for r in read_csv(path):
            n = (r.get("artist_name_en") or "").strip()
            img = (r.get("image_url") or "").strip()
            if n and img:
                out[n] = img
    return out


def load_logos():
    path = os.path.join(SCRIPTS, "agency_logos.csv")
    return {
        r["agency"]: (r.get("logo_url") or "").strip()
        for r in read_csv(path)
        if r.get("agency")
    }


def main():
    artist_images = load_artist_images()
    logos = load_logos()

    raw_path = latest(os.path.join(DATA, "raw"))
    top_path = latest(os.path.join(DATA, "song_rankings"), "top_")
    hot_path = latest(os.path.join(DATA, "song_rankings"), "hot_")
    yt_path = latest(os.path.join(DATA, "youtube_videos"))

    raw = read_csv(raw_path)
    top = read_csv(top_path)
    hot = read_csv(hot_path)
    yt_rows = read_csv(yt_path)

    report_date = ""
    if raw:
        report_date = raw[0].get("date", "")
    elif top:
        report_date = (top_path or "").split("top_")[-1].replace(".csv", "")

    # Artists
    artists = []
    for r in raw:
        name = (r.get("artist_name") or "").strip()
        agency = (r.get("agency") or "").strip() or "OTHER"
        artists.append(
            {
                "name": name,
                "agency": agency,
                "sub_agency": r.get("sub_agency", ""),
                "youtube_subscribers": safe_int(r.get("youtube_subscribers")),
                "youtube_total_views": safe_int(r.get("youtube_total_views")),
                "wikipedia_pv_ja": safe_int(r.get("wikipedia_pv_ja")),
                "wikipedia_pv_en": safe_int(r.get("wikipedia_pv_en")),
                "image_url": artist_images.get(name, "")
                or (r.get("youtube_channel_thumbnail") or "").strip(),
                "agency_logo_url": logos.get(agency, ""),
            }
        )

    # Agency power = sum of YT subscribers
    agency_map = defaultdict(lambda: {"subscribers": 0, "artists": 0, "views": 0})
    for a in artists:
        ag = a["agency"]
        agency_map[ag]["subscribers"] += a["youtube_subscribers"]
        agency_map[ag]["views"] += a["youtube_total_views"]
        agency_map[ag]["artists"] += 1

    agencies = []
    for ag, v in agency_map.items():
        agencies.append(
            {
                "agency": ag,
                "subscribers": v["subscribers"],
                "views": v["views"],
                "artists": v["artists"],
                "logo_url": logos.get(ag, ""),
            }
        )
    agencies.sort(key=lambda x: -x["subscribers"])

    def song_payload(rows):
        out = []
        for r in rows:
            vid = (r.get("youtube_video_id") or "").strip()
            out.append(
                {
                    "rank": safe_int(r.get("rank")),
                    "track_id": r.get("track_id", ""),
                    "artist": r.get("artist_name_en", ""),
                    "track": r.get("track_name", ""),
                    "agency": r.get("agency", "") or "OTHER",
                    "sub_agency": r.get("sub_agency", ""),
                    "score": safe_float(r.get("score")),
                    "chart_points": safe_float(r.get("chart_points") or r.get("chart_delta")),
                    "youtube_views": safe_int(r.get("youtube_views")),
                    "artwork_url": (r.get("artwork_url") or "").strip(),
                    "artist_image_url": (r.get("artist_image_url") or "").strip()
                    or artist_images.get(r.get("artist_name_en", ""), ""),
                    "agency_logo_url": (r.get("agency_logo_url") or "").strip()
                    or logos.get(r.get("agency", ""), ""),
                    "youtube_thumbnail_url": (r.get("youtube_thumbnail_url") or "").strip()
                    or yt_thumb(vid),
                    "youtube_video_id": vid,
                }
            )
        return out

    # YouTube videos: dedupe by video_id, keep max views,
    # prefer hot_mv > top_views > recent for same view-ish ties
    sel_bonus = {"hot_mv": 2 * 10**12, "top_views": 10**12, "recent": 0}
    best = {}
    for r in yt_rows:
        vid = (r.get("video_id") or "").strip()
        if not vid:
            continue
        views = safe_int(r.get("view_count"))
        cur = best.get(vid)
        sel = r.get("selection", "")
        score = views + sel_bonus.get(sel, 0)
        cur_score = 0
        if cur:
            cur_score = cur["view_count"] + sel_bonus.get(cur.get("selection", ""), 0)
        if not cur or score > cur_score:
            best[vid] = {
                "video_id": vid,
                "title": r.get("title", ""),
                "url": r.get("url") or f"https://www.youtube.com/watch?v={vid}",
                "artist": r.get("artist_name", ""),
                "agency": r.get("agency", "") or "OTHER",
                "sub_agency": r.get("sub_agency", ""),
                "view_count": views,
                "like_count": safe_int(r.get("like_count")),
                "comment_count": safe_int(r.get("comment_count")),
                "published_at": r.get("published_at", ""),
                "selection": r.get("selection", ""),
                "thumbnail_url": (r.get("thumbnail_url") or "").strip() or yt_thumb(vid),
                "agency_logo_url": logos.get(r.get("agency", ""), ""),
                "artist_image_url": artist_images.get(r.get("artist_name", ""), ""),
            }

    videos = sorted(best.values(), key=lambda x: -x["view_count"])

    payload = {
        "meta": {
            "title": "RIVERSTONE K-POP POWER REPORT",
            "report_date": report_date,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": {
                "raw": os.path.basename(raw_path or ""),
                "top_songs": os.path.basename(top_path or ""),
                "hot_songs": os.path.basename(hot_path or ""),
                "youtube_videos": os.path.basename(yt_path or ""),
            },
            "agencies": [a["agency"] for a in agencies],
        },
        "agencies": agencies,
        "artists": sorted(artists, key=lambda x: -x["youtube_subscribers"]),
        "top_songs": song_payload(top),
        "hot_songs": song_payload(hot),
        "youtube_videos": videos[:200],  # cap for page weight
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"Wrote {OUT}\n"
        f"  agencies={len(agencies)} artists={len(artists)} "
        f"top={len(payload['top_songs'])} hot={len(payload['hot_songs'])} "
        f"videos={len(payload['youtube_videos'])}"
    )


if __name__ == "__main__":
    main()
