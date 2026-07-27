"""
LINE MUSIC / スペースシャワーのチャート生データから外部IDを採掘し、
マスタ照合して artist_external_ids / track_external_ids を更新する。

方針:
  - Search APIよりチャート採掘が主 (両ソースともチャートJSONに安定IDがある)
  - 名前正規化で一致したら match_status=candidate (人が confirmed に昇格)
  - 不一致は unmatched として残し、OTHER候補の発見源にする
  - 同一アーティストの複数LINE IDは同じ artist_name_en の複数行として保持

実行:
  python mine_chart_ids.py
  python mine_chart_ids.py --promote-candidates   # 一意マッチを confirmed に昇格
"""

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import (
    ensure_external_id_templates,
    load_artist_external_ids,
    load_track_external_ids,
    norm_name,
    save_artist_external_ids,
    save_track_external_ids,
)
from master_data import load_all_artists

SCRIPTS_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(SCRIPTS_DIR, "..", "data")
CANDIDATES_CSV = os.path.join(SCRIPTS_DIR, "artist_external_candidates.csv")

CANDIDATE_FIELDS = [
    "platform",
    "external_artist_id",
    "observed_name",
    "suggested_artist_name_en",
    "suggested_source_file",
    "suggested_agency",
    "match_status",
    "first_seen",
    "last_seen",
    "notes",
]


def collect_from_files(
    paths,
    artist_id_col,
    track_id_col,
    artist_name_col,
    track_name_col,
    date_col,
    master_artist_col=None,
):
    artists = {}
    tracks = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                date = (row.get(date_col) or "").strip()
                aid = (row.get(artist_id_col) or "").strip()
                tid = (row.get(track_id_col) or "").strip()
                aname = (row.get(artist_name_col) or "").strip()
                tname = (row.get(track_name_col) or "").strip()
                master_artist = (
                    (row.get(master_artist_col) or "").strip() if master_artist_col else ""
                )

                if aid:
                    cur = artists.get(aid)
                    if not cur:
                        artists[aid] = {
                            "observed_name": aname,
                            "master_artist_name": master_artist,
                            "first_seen": date,
                            "last_seen": date,
                        }
                    else:
                        if date:
                            cur["last_seen"] = max(cur["last_seen"], date)
                            if not cur["first_seen"] or date < cur["first_seen"]:
                                cur["first_seen"] = date
                        if aname:
                            cur["observed_name"] = aname
                        if master_artist:
                            cur["master_artist_name"] = master_artist

                if tid:
                    cur = tracks.get(tid)
                    if not cur:
                        tracks[tid] = {
                            "observed_artist_name": aname,
                            "observed_track_name": tname,
                            "master_artist_name": master_artist,
                            "first_seen": date,
                            "last_seen": date,
                        }
                    else:
                        if date:
                            cur["last_seen"] = max(cur["last_seen"], date)
                            if not cur["first_seen"] or date < cur["first_seen"]:
                                cur["first_seen"] = date
                        if aname:
                            cur["observed_artist_name"] = aname
                        if tname:
                            cur["observed_track_name"] = tname
                        if master_artist:
                            cur["master_artist_name"] = master_artist
    return artists, tracks


def build_master_index():
    index = defaultdict(list)
    for row in load_all_artists():
        key = norm_name(row["artist_name_en"])
        if key:
            index[key].append(row)
    return index


def suggest_match(observed_name, master_index):
    key = norm_name(observed_name)
    if not key:
        return None, "empty_name"
    hits = master_index.get(key, [])
    if len(hits) == 1:
        return hits[0], "exact_name"
    if len(hits) > 1:
        return None, f"ambiguous:{[h['artist_name_en'] for h in hits]}"
    return None, "no_master_match"


def merge_artist_rows(
    existing, mined, platform, master_index, promote_candidates, id_master_lookup=None
):
    by_key = {(r["platform"], r["external_artist_id"]): dict(r) for r in existing}
    candidates_out = []
    id_master_lookup = id_master_lookup or {}

    for eid, info in mined.items():
        key = (platform, eid)
        master = id_master_lookup.get(eid)
        reason = "apple_artist_id" if master else ""
        if not master:
            master, reason = suggest_match(info["observed_name"], master_index)
            # チャート上の artist_name_master があれば優先
            chart_master = (info.get("master_artist_name") or "").strip()
            if chart_master and not master:
                # 名前で再検索
                master, reason = suggest_match(chart_master, master_index)
                if master:
                    reason = "chart_artist_name_master"
                else:
                    # マスタに無い場合でも chart の英語名を採用候補に
                    master = {
                        "artist_name_en": chart_master,
                        "_source_file": "",
                        "agency": "",
                    }
                    reason = "chart_artist_name_master_unverified"

        row = by_key.get(key)

        if row is None:
            row = {
                "platform": platform,
                "external_artist_id": eid,
                "artist_name_en": "",
                "source_file": "",
                "match_status": "unmatched",
                "observed_name": info["observed_name"],
                "first_seen": info["first_seen"],
                "last_seen": info["last_seen"],
                "notes": "",
            }
            by_key[key] = row
        else:
            row["observed_name"] = info["observed_name"] or row.get("observed_name", "")
            if info["first_seen"]:
                prev = row.get("first_seen") or info["first_seen"]
                row["first_seen"] = min(prev, info["first_seen"])
            if info["last_seen"]:
                prev = row.get("last_seen") or info["last_seen"]
                row["last_seen"] = max(prev, info["last_seen"])

        if row.get("match_status") == "confirmed" and row.get("artist_name_en"):
            pass
        elif master and master.get("artist_name_en"):
            status = "confirmed" if (
                promote_candidates or reason in ("apple_artist_id", "chart_artist_name_master", "exact_name")
            ) else "candidate"
            if reason == "chart_artist_name_master_unverified":
                status = "candidate"
            row["artist_name_en"] = master["artist_name_en"]
            row["source_file"] = master.get("_source_file", "")
            row["match_status"] = status
            row["notes"] = reason
        else:
            if row.get("match_status") not in ("confirmed", "candidate"):
                row["match_status"] = "unmatched"
                row["notes"] = reason

        candidates_out.append(
            {
                "platform": platform,
                "external_artist_id": eid,
                "observed_name": info["observed_name"],
                "suggested_artist_name_en": (master or {}).get("artist_name_en", ""),
                "suggested_source_file": (master or {}).get("_source_file", ""),
                "suggested_agency": (master or {}).get("agency", ""),
                "match_status": row["match_status"],
                "first_seen": row.get("first_seen", ""),
                "last_seen": row.get("last_seen", ""),
                "notes": row.get("notes", "") or reason,
            }
        )

    return list(by_key.values()), candidates_out


def merge_track_rows(existing, mined, platform, artist_lookup_by_observed):
    by_key = {(r["platform"], r["external_track_id"]): dict(r) for r in existing}

    for tid, info in mined.items():
        key = (platform, tid)
        observed_artist = info["observed_artist_name"]
        linked = artist_lookup_by_observed.get((platform, norm_name(observed_artist)))
        row = by_key.get(key)

        if row is None:
            row = {
                "platform": platform,
                "external_track_id": tid,
                "artist_name_en": "",
                "track_name": info["observed_track_name"],
                "source_file": "",
                "match_status": "unmatched",
                "observed_artist_name": observed_artist,
                "observed_track_name": info["observed_track_name"],
                "first_seen": info["first_seen"],
                "last_seen": info["last_seen"],
                "notes": "",
            }
            by_key[key] = row
        else:
            row["observed_artist_name"] = observed_artist or row.get("observed_artist_name", "")
            row["observed_track_name"] = info["observed_track_name"] or row.get(
                "observed_track_name", ""
            )
            if not row.get("track_name"):
                row["track_name"] = info["observed_track_name"]
            if info["first_seen"]:
                prev = row.get("first_seen") or info["first_seen"]
                row["first_seen"] = min(prev, info["first_seen"])
            if info["last_seen"]:
                prev = row.get("last_seen") or info["last_seen"]
                row["last_seen"] = max(prev, info["last_seen"])

        if row.get("match_status") == "confirmed" and row.get("artist_name_en"):
            continue

        master_artist = (info.get("master_artist_name") or "").strip()
        if master_artist:
            row["artist_name_en"] = master_artist
            row["match_status"] = "confirmed"
            row["track_name"] = row.get("track_name") or info["observed_track_name"]
            row["notes"] = "chart_artist_name_master"
            continue

        if linked and linked.get("artist_name_en"):
            row["artist_name_en"] = linked["artist_name_en"]
            row["source_file"] = linked.get("source_file", "")
            row["match_status"] = (
                "confirmed" if linked.get("match_status") == "confirmed" else "candidate"
            )
            row["track_name"] = row.get("track_name") or info["observed_track_name"]
        elif row.get("match_status") not in ("confirmed", "candidate"):
            row["match_status"] = "unmatched"

    return list(by_key.values())


def chart_paths(subdir):
    pattern = os.path.join(DATA_DIR, subdir, "[0-9][0-9][0-9][0-9]-*.csv")
    return [
        p
        for p in sorted(glob.glob(pattern))
        if not os.path.basename(p).startswith("summary_")
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--promote-candidates",
        action="store_true",
        help="一意名前マッチを confirmed に昇格する",
    )
    args = parser.parse_args()

    ensure_external_id_templates()
    master_index = build_master_index()

    sources = [
        (
            "line",
            chart_paths("line_charts"),
            "line_artist_id",
            "line_track_id",
            "artist_name_local",
            "track_name",
            "chart_date",
            "artist_name_master",
        ),
        (
            "spaceshower",
            chart_paths("spaceshower_charts"),
            "spaceshower_artist_id",
            "spaceshower_song_id",
            "artist_name_local",
            "track_name",
            "chart_date",
            "artist_name_master",
        ),
        (
            "apple",
            chart_paths("apple_charts"),
            "apple_artist_id",
            "apple_track_id",
            "artist_name_local",
            "track_name",
            "date",
            "artist_name_master",
        ),
    ]

    existing_artists = load_artist_external_ids()
    existing_tracks = load_track_external_ids()
    all_candidates = []

    apple_id_lookup = {
        r["apple_artist_id"].strip(): r
        for r in load_all_artists()
        if (r.get("apple_artist_id") or "").strip()
    }

    for platform, paths, aid_col, tid_col, aname_col, tname_col, date_col, master_col in sources:
        if not paths:
            print(f"[SKIP] {platform}: チャートCSVがありません")
            continue

        artists, tracks = collect_from_files(
            paths, aid_col, tid_col, aname_col, tname_col, date_col, master_artist_col=master_col
        )
        print(f"{platform}: artists={len(artists)} tracks={len(tracks)} from {len(paths)} files")

        id_lookup = apple_id_lookup if platform == "apple" else None
        existing_artists, cands = merge_artist_rows(
            existing_artists,
            artists,
            platform,
            master_index,
            args.promote_candidates,
            id_master_lookup=id_lookup,
        )
        all_candidates.extend(cands)

        artist_lookup_by_observed = {}
        for r in existing_artists:
            if r.get("platform") != platform:
                continue
            if r.get("match_status") in ("confirmed", "candidate") and r.get("artist_name_en"):
                artist_lookup_by_observed[(platform, norm_name(r.get("observed_name", "")))] = r
                artist_lookup_by_observed[(platform, norm_name(r["artist_name_en"]))] = r

        existing_tracks = merge_track_rows(
            existing_tracks, tracks, platform, artist_lookup_by_observed
        )

    existing_artists.sort(key=lambda r: (r.get("platform", ""), r.get("external_artist_id", "")))
    existing_tracks.sort(key=lambda r: (r.get("platform", ""), r.get("external_track_id", "")))
    all_candidates.sort(key=lambda r: (r.get("platform", ""), r.get("external_artist_id", "")))

    save_artist_external_ids(existing_artists)
    save_track_external_ids(existing_tracks)

    with open(CANDIDATES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
        w.writeheader()
        w.writerows(all_candidates)

    def count_status(rows, platform=None):
        c = defaultdict(int)
        for r in rows:
            if platform and r.get("platform") != platform:
                continue
            c[r.get("match_status", "")] += 1
        return dict(c)

    print(f"\n保存: artist_external_ids.csv ({len(existing_artists)}行)")
    print(f"保存: track_external_ids.csv ({len(existing_tracks)}行)")
    print(f"保存: artist_external_candidates.csv ({len(all_candidates)}行)")
    print("\n--- artist match_status ---")
    for platform in ("line", "spaceshower", "apple"):
        print(f"  {platform}: {count_status(existing_artists, platform)}")
    print("--- track match_status ---")
    for platform in ("line", "spaceshower", "apple"):
        print(f"  {platform}: {count_status(existing_tracks, platform)}")


if __name__ == "__main__":
    main()
