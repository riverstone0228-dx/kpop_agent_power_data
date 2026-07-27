"""
楽曲ランキング: TOP SONG 20 / HOT SONG 20

前提:
  - scripts/track_master.csv (build_track_master.py で生成)
  - Apple / LINE / Space Shower チャートCSV
  - (任意) data/youtube_videos/ の累積再生・いいね・コメント

スコア設計:
  TOP SONG 20 (定着・総合)
    - 直近7日チャート加点 (LINE / Apple jp·kr / SSTV直近2週)
      各出現: (chart_size - rank + 1)
    - YouTube累積再生 log1p を副指標 (データがある場合 70:30)

  HOT SONG 20 (勢い)
    - 直近3日チャート加点 − その前3日チャート加点 (デルタ)
    - LINE is_new / 順位上昇ボーナス
    - YouTube: 同一 track の view/like/comment (当日スナップ) を副指標
      ※日次差分は履歴が溜まり次第強化可能

出力:
  data/song_rankings/top_YYYY-MM-DD.csv
  data/song_rankings/hot_YYYY-MM-DD.csv

実行:
  python rank_songs.py
  python rank_songs.py 2026-07-27
"""

from __future__ import annotations

import csv
import datetime
import glob
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import norm_name
from build_track_master import make_track_id, TRACK_MASTER_CSV

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LINE_DIR = os.path.join(DATA_DIR, "line_charts")
APPLE_DIR = os.path.join(DATA_DIR, "apple_charts")
SSTV_DIR = os.path.join(DATA_DIR, "spaceshower_charts")
YT_DIR = os.path.join(DATA_DIR, "youtube_videos")
OUT_DIR = os.path.join(DATA_DIR, "song_rankings")

TOP_N = 20
LINE_LOOKBACK = 7
APPLE_LOOKBACK = 7
SSTV_FILES = 2
HOT_RECENT_DAYS = 3
HOT_PREV_DAYS = 3
CHART_WEIGHT = 0.70
YT_WEIGHT = 0.30


def load_track_master():
    if not os.path.exists(TRACK_MASTER_CSV):
        return []
    with open(TRACK_MASTER_CSV, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("status") or "active") == "active"]


def chart_files(directory, dates=None, max_files=None):
    files = sorted(
        [
            p
            for p in glob.glob(os.path.join(directory, "[0-9][0-9][0-9][0-9]-*.csv"))
            if not os.path.basename(p).startswith("summary_")
        ],
        reverse=True,
    )
    if dates is not None:
        files = [p for p in files if os.path.basename(p).replace(".csv", "") in dates]
    if max_files is not None:
        files = files[:max_files]
    return files


def resolve_track_id(artist_master, track_name, master_index, external_index):
    """master_index: (norm_artist, norm_track) -> track_id
    external_index: (platform, external_id) -> track_id
    """
    if artist_master and track_name:
        key = (norm_name(artist_master), norm_name(track_name))
        if key in master_index:
            return master_index[key]
        # 部分一致 (feat. 除去など緩い)
        a, t = key
        for (ma, mt), tid in master_index.items():
            if ma == a and (t in mt or mt in t) and min(len(t), len(mt)) >= 4:
                return tid
    return ""


def build_indexes(tracks):
    master_index = {}
    by_id = {}
    for r in tracks:
        tid = r["track_id"]
        by_id[tid] = r
        master_index[(norm_name(r["artist_name_en"]), norm_name(r["track_name"]))] = tid
    return master_index, by_id


def add_points(bucket, tid, rank, chart_size, weight=1.0):
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return
    points = max(chart_size - rank + 1, 1) * weight
    bucket[tid] += points


def accumulate_charts(as_of: datetime.date, lookback_days: int, master_index):
    """tid -> chart points, platforms, extras"""
    scores = defaultdict(float)
    platforms = defaultdict(set)
    extras = defaultdict(lambda: {"is_new": 0, "rank_up": 0})

    # LINE
    line_dates = {
        (as_of - datetime.timedelta(days=i)).isoformat() for i in range(lookback_days)
    }
    for path in chart_files(LINE_DIR, dates=line_dates):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        size = len(rows) or 50
        for r in rows:
            tid = resolve_track_id(
                r.get("artist_name_master", ""), r.get("track_name", ""), master_index, {}
            )
            if not tid:
                # マスタ未登録でも matched artist+track で一時ID
                artist = (r.get("artist_name_master") or "").strip()
                track = (r.get("track_name") or "").strip()
                if not artist or not track:
                    continue
                tid = make_track_id(artist, track)
            add_points(scores, tid, r.get("rank"), size)
            platforms[tid].add("line")
            if (r.get("is_new") or "").lower() in ("1", "true", "yes"):
                extras[tid]["is_new"] += 1
            try:
                rv = int(r.get("rank_variation") or 0)
                if rv > 0:
                    extras[tid]["rank_up"] += rv
            except ValueError:
                pass

    # Apple jp/kr
    apple_dates = {
        (as_of - datetime.timedelta(days=i)).isoformat() for i in range(lookback_days)
    }
    for path in chart_files(APPLE_DIR, dates=apple_dates):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        by_country = defaultdict(list)
        for r in rows:
            if r.get("country") not in ("jp", "kr"):
                continue
            if not (r.get("artist_name_master") or "").strip() and r.get("is_kpop_genre") != "1":
                continue
            by_country[r["country"]].append(r)
        for country, country_rows in by_country.items():
            size = len([r for r in rows if r.get("country") == country]) or 100
            for r in country_rows:
                artist = (r.get("artist_name_master") or "").strip()
                track = (r.get("track_name") or "").strip()
                if not track:
                    continue
                tid = resolve_track_id(artist, track, master_index, {})
                if not tid and artist:
                    tid = make_track_id(artist, track)
                if not tid:
                    continue
                add_points(scores, tid, r.get("rank"), size)
                platforms[tid].add(f"apple_{country}")

    # Space Shower: ファイル数ベース
    for path in chart_files(SSTV_DIR, max_files=SSTV_FILES):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        size = len(rows) or 40
        for r in rows:
            artist = (r.get("artist_name_master") or "").strip()
            track = (r.get("track_name") or "").strip()
            if not artist or not track:
                continue
            tid = resolve_track_id(artist, track, master_index, {}) or make_track_id(artist, track)
            add_points(scores, tid, r.get("rank"), size)
            platforms[tid].add("spaceshower")

    return scores, platforms, extras


def load_youtube_by_track(master_by_id):
    """track_id -> best youtube stats from latest file."""
    files = chart_files(YT_DIR, max_files=1)
    if not files:
        return {}
    with open(files[0], newline="", encoding="utf-8") as f:
        yt_rows = list(csv.DictReader(f))

    # video_id -> track
    by_video = {
        r["youtube_video_id"]: r["track_id"]
        for r in master_by_id.values()
        if r.get("youtube_video_id")
    }
    out = {}
    for r in yt_rows:
        vid = r.get("video_id", "")
        tid = by_video.get(vid)
        if not tid:
            # タイトル照合
            artist = (r.get("artist_name") or "").strip()
            title = r.get("title") or ""
            for t in master_by_id.values():
                if t["artist_name_en"] != artist:
                    continue
                if norm_name(t["track_name"]) and norm_name(t["track_name"]) in norm_name(title):
                    tid = t["track_id"]
                    break
        if not tid:
            continue
        try:
            views = int(r.get("view_count") or 0)
            likes = int(r.get("like_count") or 0)
            comments = int(r.get("comment_count") or 0)
        except ValueError:
            views = likes = comments = 0
        cur = out.get(tid)
        if not cur or views > cur["views"]:
            out[tid] = {"views": views, "likes": likes, "comments": comments, "video_id": vid}
    return out


def normalize(values):
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def ensure_meta(tid, master_by_id):
    if tid in master_by_id:
        r = master_by_id[tid]
        return {
            "track_id": tid,
            "artist_name_en": r.get("artist_name_en", ""),
            "track_name": r.get("track_name", ""),
            "agency": r.get("agency", ""),
            "sub_agency": r.get("sub_agency", ""),
            "youtube_video_id": r.get("youtube_video_id", ""),
        }
    # ephemeral
    return {
        "track_id": tid,
        "artist_name_en": "",
        "track_name": "",
        "agency": "",
        "sub_agency": "",
        "youtube_video_id": "",
    }


def rank_top(as_of: datetime.date, tracks):
    master_index, master_by_id = build_indexes(tracks)
    chart, platforms, _ = accumulate_charts(as_of, LINE_LOOKBACK, master_index)
    yt = load_youtube_by_track(master_by_id)

    # 候補: チャートに出た曲 + マスタ曲
    candidates = set(chart.keys()) | set(master_by_id.keys())
    yt_vals = {t: math.log1p(yt[t]["views"]) for t in candidates if t in yt and yt[t]["views"]}
    has_yt = bool(yt_vals)
    chart_n = normalize({t: chart.get(t, 0.0) for t in candidates})
    yt_n = normalize(yt_vals) if has_yt else {}

    rows = []
    for tid in candidates:
        meta = ensure_meta(tid, master_by_id)
        if not meta["artist_name_en"] and tid.startswith("trk_"):
            # ephemeral without names — skip empty shells
            if chart.get(tid, 0) <= 0:
                continue
        c = chart_n.get(tid, 0.0)
        y = yt_n.get(tid, 0.0) if has_yt else 0.0
        score = CHART_WEIGHT * c + YT_WEIGHT * y if has_yt else c
        if chart.get(tid, 0) <= 0 and y <= 0:
            continue
        rows.append(
            {
                **meta,
                "score": round(score, 6),
                "chart_points": round(chart.get(tid, 0.0), 1),
                "chart_norm": round(c, 4),
                "youtube_views": yt.get(tid, {}).get("views", ""),
                "youtube_norm": round(y, 4) if has_yt else "",
                "platforms_hit": len(platforms.get(tid, set())),
                "platforms": "|".join(sorted(platforms.get(tid, set()))),
            }
        )

    rows.sort(key=lambda r: (-r["score"], -r["chart_points"], r["artist_name_en"], r["track_name"]))
    return rows[:TOP_N], has_yt


def rank_hot(as_of: datetime.date, tracks):
    master_index, master_by_id = build_indexes(tracks)

    recent_scores, recent_plat, extras = accumulate_charts(
        as_of, HOT_RECENT_DAYS, master_index
    )
    prev_as_of = as_of - datetime.timedelta(days=HOT_RECENT_DAYS)
    prev_scores, _, _ = accumulate_charts(prev_as_of, HOT_PREV_DAYS, master_index)

    yt = load_youtube_by_track(master_by_id)

    candidates = set(recent_scores) | set(prev_scores)
    delta = {t: recent_scores.get(t, 0.0) - prev_scores.get(t, 0.0) for t in candidates}

    # ボーナス込み raw
    raw = {}
    for tid in candidates:
        bonus = extras[tid]["is_new"] * 20 + min(extras[tid]["rank_up"], 50)
        raw[tid] = delta.get(tid, 0.0) + bonus

    yt_eng = {}
    for tid in candidates:
        if tid not in yt:
            continue
        # エンゲージメント密度
        v = yt[tid]["views"] or 1
        yt_eng[tid] = math.log1p(yt[tid]["likes"] + yt[tid]["comments"] * 2) + math.log1p(v) * 0.1

    has_yt = bool(yt_eng)
    raw_n = normalize(raw)
    yt_n = normalize(yt_eng) if has_yt else {}

    rows = []
    for tid in candidates:
        meta = ensure_meta(tid, master_by_id)
        r = raw_n.get(tid, 0.0)
        y = yt_n.get(tid, 0.0) if has_yt else 0.0
        score = CHART_WEIGHT * r + YT_WEIGHT * y if has_yt else r
        if recent_scores.get(tid, 0) <= 0 and delta.get(tid, 0) <= 0 and y <= 0:
            continue
        rows.append(
            {
                **meta,
                "score": round(score, 6),
                "chart_delta": round(delta.get(tid, 0.0), 1),
                "chart_recent": round(recent_scores.get(tid, 0.0), 1),
                "chart_prev": round(prev_scores.get(tid, 0.0), 1),
                "is_new_hits": extras[tid]["is_new"],
                "youtube_likes": yt.get(tid, {}).get("likes", ""),
                "youtube_comments": yt.get(tid, {}).get("comments", ""),
                "youtube_views": yt.get(tid, {}).get("views", ""),
                "platforms_hit": len(recent_plat.get(tid, set())),
                "platforms": "|".join(sorted(recent_plat.get(tid, set()))),
            }
        )

    rows.sort(key=lambda r: (-r["score"], -r["chart_delta"], r["artist_name_en"], r["track_name"]))
    return rows[:TOP_N], has_yt


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            w.writerow({"rank": i, **r})


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    as_of = datetime.date.fromisoformat(date_str)
    tracks = load_track_master()
    if not tracks:
        print("track_master.csv が空です。先に mine_chart_ids.py → build_track_master.py を実行してください。")
        return

    top_rows, top_yt = rank_top(as_of, tracks)
    hot_rows, hot_yt = rank_hot(as_of, tracks)

    top_fields = [
        "rank",
        "track_id",
        "artist_name_en",
        "track_name",
        "agency",
        "sub_agency",
        "score",
        "chart_points",
        "chart_norm",
        "youtube_views",
        "youtube_norm",
        "platforms_hit",
        "platforms",
        "youtube_video_id",
    ]
    hot_fields = [
        "rank",
        "track_id",
        "artist_name_en",
        "track_name",
        "agency",
        "sub_agency",
        "score",
        "chart_delta",
        "chart_recent",
        "chart_prev",
        "is_new_hits",
        "youtube_views",
        "youtube_likes",
        "youtube_comments",
        "platforms_hit",
        "platforms",
        "youtube_video_id",
    ]

    top_path = os.path.join(OUT_DIR, f"top_{date_str}.csv")
    hot_path = os.path.join(OUT_DIR, f"hot_{date_str}.csv")
    write_csv(top_path, top_rows, top_fields)
    write_csv(hot_path, hot_rows, hot_fields)

    print(f"TOP SONG {TOP_N} → {top_path} (yt副指標={'ON' if top_yt else 'OFF'})")
    for i, r in enumerate(top_rows[:10], start=1):
        print(f"  {i:2d}. {r['artist_name_en']} - {r['track_name']} ({r['score']})")
    print(f"HOT SONG {TOP_N} → {hot_path} (yt副指標={'ON' if hot_yt else 'OFF'})")
    for i, r in enumerate(hot_rows[:10], start=1):
        print(f"  {i:2d}. {r['artist_name_en']} - {r['track_name']} delta={r['chart_delta']}")


if __name__ == "__main__":
    main()
