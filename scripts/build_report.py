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


def days_age(published_at: str, as_of: str) -> int:
    """公開日から as_of までの日数。不明なら 14。"""
    pub = (published_at or "")[:10]
    ref = (as_of or "")[:10]
    if not pub:
        return 14
    try:
        p = datetime.strptime(pub, "%Y-%m-%d").date()
        if ref:
            t = datetime.strptime(ref, "%Y-%m-%d").date()
        else:
            t = datetime.now(timezone.utc).date()
        return max((t - p).days, 0)
    except ValueError:
        return 14


def video_hot_score(views: int, published_at: str, as_of: str) -> float:
    """勢い指標: 再生 ÷ (日齢 + 7)。『直近でどれだけ伸びているか』の代理。"""
    return views / (days_age(published_at, as_of) + 7)


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
    elif yt_path:
        report_date = os.path.basename(yt_path).replace(".csv", "")

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

    # YouTube HOT: 急上昇・人気 MV
    #  - 優先: selection=hot_mv（直近uploads × 10分以下 × 音楽寄り × views/(日齢+7)）
    #  - 無い日は全動画から同指標でフォールバック
    #  昨日比の日次差分ではなく「公開日からの勢い」指標（履歴が無くても当日だけで出せる）
    sel_prefer = {"hot_mv": 3, "recent": 2, "top_views": 1}
    pool = [r for r in yt_rows if (r.get("selection") or "") == "hot_mv"]
    used_hot_mv = bool(pool)
    if not pool:
        pool = yt_rows

    best_hot = {}
    for r in pool:
        vid = (r.get("video_id") or "").strip()
        if not vid:
            continue
        views = safe_int(r.get("view_count"))
        pub = r.get("published_at", "")
        age = days_age(pub, report_date)
        hot_score = video_hot_score(views, pub, report_date)
        sel = r.get("selection", "")
        # 同一 video が複数 selection にある場合は hot_mv を優先
        cur = best_hot.get(vid)
        prefer = sel_prefer.get(sel, 0)
        if cur and (prefer < sel_prefer.get(cur.get("selection", ""), 0)):
            continue
        if cur and prefer == sel_prefer.get(cur.get("selection", ""), 0) and hot_score <= cur["hot_score"]:
            continue
        best_hot[vid] = {
            "video_id": vid,
            "title": r.get("title", ""),
            "url": r.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "artist": r.get("artist_name", ""),
            "agency": r.get("agency", "") or "OTHER",
            "sub_agency": r.get("sub_agency", ""),
            "view_count": views,
            "like_count": safe_int(r.get("like_count")),
            "comment_count": safe_int(r.get("comment_count")),
            "published_at": pub,
            "selection": sel,
            "age_days": age,
            "hot_score": round(hot_score, 2),
            "views_per_day": round(views / (age + 1), 1) if age is not None else 0,
            "duration_sec": safe_int(r.get("duration_sec")) if r.get("duration_sec") not in ("", None) else None,
            "thumbnail_url": (r.get("thumbnail_url") or "").strip() or yt_thumb(vid),
            "agency_logo_url": logos.get(r.get("agency", ""), ""),
            "artist_image_url": artist_images.get(r.get("artist_name", ""), ""),
        }

    youtube_hot = sorted(best_hot.values(), key=lambda x: -x["hot_score"])

    # 後方互換: 旧 TOP（累積再生）も残す（Pages は HOT を表示）
    best_top = {}
    for r in yt_rows:
        vid = (r.get("video_id") or "").strip()
        if not vid:
            continue
        views = safe_int(r.get("view_count"))
        cur = best_top.get(vid)
        if not cur or views > cur["view_count"]:
            best_top[vid] = {
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
    youtube_videos = sorted(best_top.values(), key=lambda x: -x["view_count"])

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
            "youtube_hot_method": (
                "hot_mv first; score = view_count / (age_days+7). "
                "Not day-over-day delta (needs more history). "
                "hot_mv pool: recent uploads, duration≤10m, music-oriented."
                if used_hot_mv
                else "fallback velocity on all videos (hot_mv not in CSV yet); "
                "score = view_count / (age_days+7)"
            ),
            "agencies": [a["agency"] for a in agencies],
        },
        "agencies": agencies,
        "artists": sorted(artists, key=lambda x: -x["youtube_subscribers"]),
        "top_songs": song_payload(top),
        "hot_songs": song_payload(hot),
        "youtube_hot": youtube_hot[:80],
        "youtube_videos": youtube_videos[:200],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"Wrote {OUT}\n"
        f"  agencies={len(agencies)} artists={len(artists)} "
        f"top={len(payload['top_songs'])} hot={len(payload['hot_songs'])} "
        f"yt_hot={len(payload['youtube_hot'])} "
        f"videos={len(payload['youtube_videos'])} "
        f"method={'hot_mv' if used_hot_mv else 'fallback'}"
    )


if __name__ == "__main__":
    main()
