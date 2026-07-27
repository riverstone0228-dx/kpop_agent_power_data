"""
artist_external_ids.csv / track_external_ids.csv の読み書き共通モジュール。

LINEは同一アーティストに複数IDが付くことがあるため、マスタ本体への横持ちではなく
(platform, external_*_id) の縦持ちマップで名寄せする。
"""

import csv
import os
import re

SCRIPTS_DIR = os.path.dirname(__file__)

ARTIST_EXTERNAL_CSV = os.path.join(SCRIPTS_DIR, "artist_external_ids.csv")
TRACK_EXTERNAL_CSV = os.path.join(SCRIPTS_DIR, "track_external_ids.csv")

ARTIST_EXTERNAL_FIELDS = [
    "platform",
    "external_artist_id",
    "artist_name_en",
    "source_file",
    "match_status",
    "observed_name",
    "first_seen",
    "last_seen",
    "notes",
]

TRACK_EXTERNAL_FIELDS = [
    "platform",
    "external_track_id",
    "artist_name_en",
    "track_name",
    "source_file",
    "match_status",
    "observed_artist_name",
    "observed_track_name",
    "first_seen",
    "last_seen",
    "notes",
]


def norm_name(name: str) -> str:
    """大文字小文字・記号を無視した照合キー。"""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_csv(path, fieldnames=None):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def load_artist_external_ids():
    return load_csv(ARTIST_EXTERNAL_CSV, ARTIST_EXTERNAL_FIELDS)


def save_artist_external_ids(rows):
    save_csv(ARTIST_EXTERNAL_CSV, ARTIST_EXTERNAL_FIELDS, rows)


def load_track_external_ids():
    return load_csv(TRACK_EXTERNAL_CSV, TRACK_EXTERNAL_FIELDS)


def save_track_external_ids(rows):
    save_csv(TRACK_EXTERNAL_CSV, TRACK_EXTERNAL_FIELDS, rows)


def build_artist_lookup(platform, statuses=("confirmed", "candidate")):
    """
    platform別の external_artist_id -> マスタ情報 辞書。
    match_status が statuses に含まれる行のみ。
    """
    lookup = {}
    for row in load_artist_external_ids():
        if row.get("platform") != platform:
            continue
        if row.get("match_status") not in statuses:
            continue
        if not (row.get("artist_name_en") or "").strip():
            continue
        eid = (row.get("external_artist_id") or "").strip()
        if eid:
            lookup[eid] = row
    return lookup


def ensure_external_id_templates():
    """空の雛形CSVが無ければ作る。"""
    if not os.path.exists(ARTIST_EXTERNAL_CSV):
        save_artist_external_ids([])
    if not os.path.exists(TRACK_EXTERNAL_CSV):
        save_track_external_ids([])
