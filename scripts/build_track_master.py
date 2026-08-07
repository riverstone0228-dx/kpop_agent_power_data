"""
track_external_ids (+ YouTube動画CSV) から track_master.csv を組み立てる。

方針:
  - 確定単位は (artist_name_en, 正規化track_name)
  - platform横断の external_track_id は track_external_ids に残し、
    track_master には canonical 名と代表 youtube_video_id を持つ
  - 既存の active 行は上書きせずマージ (youtube_video_id / release_date は空なら埋める)

実行:
  python build_track_master.py
"""

from __future__ import annotations

import csv
import glob
import hashlib
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import load_track_external_ids, norm_name
from master_data import load_all_artists

SCRIPTS_DIR = os.path.dirname(__file__)
TRACK_MASTER_CSV = os.path.join(SCRIPTS_DIR, "track_master.csv")
YT_VIDEOS_DIR = os.path.join(SCRIPTS_DIR, "..", "data", "youtube_videos")

TRACK_MASTER_FIELDS = [
    "track_id",
    "agency",
    "sub_agency",
    "artist_name_en",
    "track_name",
    "release_date",
    "track_type",
    "youtube_video_id",
    "artwork_url",
    "selection_reason",
    "status",
    "platforms",
    "first_seen",
    "last_seen",
]


def make_track_id(artist_name_en: str, track_name: str) -> str:
    key = f"{norm_name(artist_name_en)}|{norm_name(track_name)}"
    return "trk_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def load_existing_master():
    if not os.path.exists(TRACK_MASTER_CSV):
        return {}
    with open(TRACK_MASTER_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id = {}
    for r in rows:
        tid = r.get("track_id") or make_track_id(r.get("artist_name_en", ""), r.get("track_name", ""))
        by_id[tid] = dict(r)
        by_id[tid]["track_id"] = tid
    return by_id


def latest_youtube_videos():
    files = sorted(glob.glob(os.path.join(YT_VIDEOS_DIR, "[0-9][0-9][0-9][0-9]-*.csv")))
    if not files:
        return []
    with open(files[-1], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def suggest_youtube_id(artist_name: str, track_name: str, yt_rows: list[dict]) -> str:
    """タイトルに曲名が含まれる公式ch動画を優先 (hot_mv > top_views > recent)。"""
    tkey = norm_name(track_name)
    if not tkey or len(tkey) < 3:
        return ""
    candidates = []
    sel_bonus = {"hot_mv": 0, "top_views": 10**6, "recent": 2 * 10**6}
    for r in yt_rows:
        if (r.get("artist_name") or "").strip() != artist_name:
            continue
        title_key = norm_name(r.get("title", ""))
        if tkey not in title_key:
            continue
        sel = r.get("selection", "")
        try:
            views = int(r.get("view_count") or 0)
        except ValueError:
            views = 0
        # Official MV っぽいものを少し優遇
        title = r.get("title") or ""
        bonus = 0
        if "M/V" in title or "MV" in title or "Official" in title:
            bonus = 10**12
        rank = int(r.get("rank") or 99)
        # スコア大ほど優先: 大きいボーナス − 弱い selection ペナルティ + views − rank
        score = bonus + views - sel_bonus.get(sel, 3 * 10**6) - rank
        candidates.append((score, r.get("video_id", "")))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]


def build_from_external_ids():
    artists = {r["artist_name_en"]: r for r in load_all_artists()}
    groups = defaultdict(lambda: {
        "track_names": [],
        "platforms": set(),
        "first_seen": "",
        "last_seen": "",
        "artist_name_en": "",
        "reasons": set(),
    })

    for row in load_track_external_ids():
        if row.get("match_status") not in ("confirmed", "candidate"):
            continue
        artist = (row.get("artist_name_en") or "").strip()
        track = (row.get("track_name") or row.get("observed_track_name") or "").strip()
        if not artist or not track:
            continue
        tid = make_track_id(artist, track)
        g = groups[tid]
        g["artist_name_en"] = artist
        g["track_names"].append(track)
        g["platforms"].add(row.get("platform", ""))
        g["reasons"].add(f"chart:{row.get('platform', '')}")
        fs, ls = row.get("first_seen", ""), row.get("last_seen", "")
        if fs:
            g["first_seen"] = min(g["first_seen"], fs) if g["first_seen"] else fs
        if ls:
            g["last_seen"] = max(g["last_seen"], ls) if g["last_seen"] else ls

    yt_rows = latest_youtube_videos()
    existing = load_existing_master()
    out = dict(existing)  # track_id -> row

    for tid, g in groups.items():
        # 最も長い表記を canonical に (情報量優先)
        track_name = sorted(g["track_names"], key=lambda s: (-len(s), s))[0]
        artist = g["artist_name_en"]
        master = artists.get(artist, {})
        yt_id = suggest_youtube_id(artist, track_name, yt_rows)

        prev = out.get(tid, {})
        platforms = sorted(set(filter(None, g["platforms"])) | set(
            (prev.get("platforms") or "").split("|") if prev.get("platforms") else []
        ))
        reasons = sorted(g["reasons"])
        if prev.get("selection_reason"):
            for part in prev["selection_reason"].split("|"):
                if part and part not in reasons:
                    reasons.append(part)

        row = {
            "track_id": tid,
            "agency": prev.get("agency") or master.get("agency", ""),
            "sub_agency": prev.get("sub_agency") or master.get("sub_agency", ""),
            "artist_name_en": artist,
            "track_name": prev.get("track_name") or track_name,
            "release_date": prev.get("release_date", ""),
            "track_type": prev.get("track_type") or "chart",
            "youtube_video_id": prev.get("youtube_video_id") or yt_id,
            "artwork_url": prev.get("artwork_url", ""),
            "selection_reason": "|".join(reasons),
            "status": prev.get("status") or "active",
            "platforms": "|".join(p for p in platforms if p),
            "first_seen": min(filter(None, [prev.get("first_seen", ""), g["first_seen"]]), default=""),
            "last_seen": max(filter(None, [prev.get("last_seen", ""), g["last_seen"]]), default=""),
        }
        # youtube が新たに付いたら理由に追加
        if row["youtube_video_id"] and "youtube" not in row["selection_reason"]:
            row["selection_reason"] = (row["selection_reason"] + "|youtube").strip("|")
            if "youtube" not in row["platforms"]:
                row["platforms"] = (row["platforms"] + "|youtube").strip("|")
        out[tid] = row

    rows = list(out.values())
    rows.sort(key=lambda r: (r.get("agency", ""), r.get("artist_name_en", ""), r.get("track_name", "")))
    return rows


def main():
    rows = build_from_external_ids()
    with open(TRACK_MASTER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACK_MASTER_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TRACK_MASTER_FIELDS})

    with_yt = sum(1 for r in rows if r.get("youtube_video_id"))
    platforms = defaultdict(int)
    for r in rows:
        for p in (r.get("platforms") or "").split("|"):
            if p:
                platforms[p] += 1

    print(f"track_master.csv: {len(rows)}曲 (youtube_video_idあり {with_yt})")
    print("platforms:", dict(platforms))


if __name__ == "__main__":
    main()
