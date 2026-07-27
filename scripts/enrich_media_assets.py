"""
レポート用メディアURLをマスタへ反映する。

優先順位:
  アーティスト画像: LINE artist.imageUrl > YouTube channel thumbnail (default)
  楽曲ジャケット: Apple artworkUrl (300px) > LINE album.imageUrl
  事務所ロゴ: agency_logos.csv (空なら Wikipedia page summary の thumbnail)
  YouTube動画サムネ: videos.list snippet.thumbnails.default (収集時に付与)

実行:
  python enrich_media_assets.py
"""

from __future__ import annotations

import csv
import glob
import os
import sys
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import norm_name

SCRIPTS_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(SCRIPTS_DIR, "..", "data")
AGENCY_LOGOS_CSV = os.path.join(SCRIPTS_DIR, "agency_logos.csv")
ARTIST_MASTER = os.path.join(SCRIPTS_DIR, "artist_master.csv")
OTHER_MASTER = os.path.join(SCRIPTS_DIR, "other_agency_master.csv")
TRACK_MASTER = os.path.join(SCRIPTS_DIR, "track_master.csv")

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)"
}

AGENCY_WIKI = {
    "HYBE": "HYBE",
    "JYP": "JYP Entertainment",
    "YG": "YG Entertainment",
    "SM": "SM Entertainment",
}


def latest_csv(directory: str):
    files = [
        p
        for p in glob.glob(os.path.join(directory, "[0-9][0-9][0-9][0-9]-*.csv"))
        if not os.path.basename(p).startswith("summary_")
    ]
    if not files:
        return None
    # ファイル名日付より「最後に書いたもの」を優先 (UTC日付ズレ対策)
    return max(files, key=os.path.getmtime)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def apple_artwork_larger(url: str) -> str:
    """100x100bb → 300x300bb (Apple CDNの慣例)。"""
    if not url:
        return ""
    return url.replace("100x100bb", "300x300bb").replace("/100x100", "/300x300")


def collect_line_images():
    path = latest_csv(os.path.join(DATA_DIR, "line_charts"))
    artist_img = {}
    track_img = {}
    if not path:
        return artist_img, track_img
    for r in read_csv(path):
        artist = (r.get("artist_name_master") or "").strip()
        track = (r.get("track_name") or "").strip()
        aimg = (r.get("artist_image_url") or "").strip()
        jimg = (r.get("album_image_url") or "").strip()
        if artist and aimg:
            artist_img[artist] = aimg
        if artist and track and jimg:
            track_img[(norm_name(artist), norm_name(track))] = jimg
    return artist_img, track_img


def collect_apple_artwork():
    path = latest_csv(os.path.join(DATA_DIR, "apple_charts"))
    out = {}
    if not path:
        return out
    for r in read_csv(path):
        artist = (r.get("artist_name_master") or "").strip()
        track = (r.get("track_name") or "").strip()
        art = apple_artwork_larger((r.get("artwork_url") or "").strip())
        if artist and track and art:
            key = (norm_name(artist), norm_name(track))
            # jp を優先したいので既にあればスキップしないが、空なら入れる
            if key not in out or r.get("country") == "jp":
                out[key] = art
    return out


def collect_youtube_channel_thumbs():
    """data/raw の最新から youtube_channel_thumbnail、なければ空。"""
    path = latest_csv(os.path.join(DATA_DIR, "raw"))
    out = {}
    if not path:
        return out
    for r in read_csv(path):
        name = (r.get("artist_name") or "").strip()
        thumb = (r.get("youtube_channel_thumbnail") or "").strip()
        if name and thumb:
            out[name] = thumb
    return out


def wiki_thumbnail(title: str) -> str:
    if not title:
        return ""
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""
        thumb = (resp.json().get("thumbnail") or {}).get("source", "")
        return thumb or ""
    except Exception:
        return ""


def enrich_agency_logos():
    """静的CSVを優先。logo_urlが空の事務所だけ Wikipedia summary で補完。"""
    rows = read_csv(AGENCY_LOGOS_CSV)
    if not rows:
        rows = [{"agency": a, "logo_url": "", "source": "", "notes": ""} for a in AGENCY_WIKI]
    fields = ["agency", "logo_url", "source", "notes"]
    by_agency = {r["agency"]: r for r in rows}
    for agency, title in AGENCY_WIKI.items():
        row = by_agency.get(agency) or {"agency": agency, "logo_url": "", "source": "", "notes": ""}
        if not (row.get("logo_url") or "").strip():
            url = wiki_thumbnail(title)
            if url:
                row["logo_url"] = url
                row["source"] = "wikipedia_summary"
                row["notes"] = title
                print(f"agency logo {agency}: {url[:80]}...")
        by_agency[agency] = row
    if "OTHER" not in by_agency:
        by_agency["OTHER"] = {"agency": "OTHER", "logo_url": "", "source": "", "notes": ""}
    out = [by_agency[a] for a in ("HYBE", "JYP", "YG", "SM", "OTHER") if a in by_agency]
    for a, row in by_agency.items():
        if a not in ("HYBE", "JYP", "YG", "SM", "OTHER"):
            out.append(row)
    write_csv(AGENCY_LOGOS_CSV, out, fields)
    return {r["agency"]: r.get("logo_url", "") for r in out}


def upsert_column(rows, col):
    """行に列が無ければ空で追加。fieldnames用。"""
    for r in rows:
        r.setdefault(col, "")
    return rows


def enrich_artist_masters(line_artists, yt_thumbs):
    for path in (ARTIST_MASTER, OTHER_MASTER):
        rows = read_csv(path)
        if not rows:
            continue
        upsert_column(rows, "image_url")
        updated = 0
        for r in rows:
            name = r.get("artist_name_en", "")
            current = (r.get("image_url") or "").strip()
            candidate = line_artists.get(name) or yt_thumbs.get(name) or ""
            # LINE優先で上書き (より高解像度)、空なら埋める
            if line_artists.get(name):
                if current != line_artists[name]:
                    r["image_url"] = line_artists[name]
                    updated += 1
            elif not current and candidate:
                r["image_url"] = candidate
                updated += 1
        fields = list(rows[0].keys())
        if "image_url" not in fields:
            fields.append("image_url")
        write_csv(path, rows, fields)
        print(f"{os.path.basename(path)}: image_url 更新 {updated} / {len(rows)}")


def enrich_track_master(apple_art, line_art):
    rows = read_csv(TRACK_MASTER)
    if not rows:
        print("track_master.csv が空です")
        return
    upsert_column(rows, "artwork_url")
    updated = 0
    for r in rows:
        key = (norm_name(r.get("artist_name_en", "")), norm_name(r.get("track_name", "")))
        art = apple_art.get(key) or line_art.get(key) or ""
        if art and (r.get("artwork_url") or "") != art:
            # Apple優先: appleにあれば採用
            if key in apple_art:
                r["artwork_url"] = apple_art[key]
                updated += 1
            elif not (r.get("artwork_url") or "").strip():
                r["artwork_url"] = art
                updated += 1
    fields = list(rows[0].keys())
    if "artwork_url" not in fields:
        fields.append("artwork_url")
    write_csv(TRACK_MASTER, rows, fields)
    with_art = sum(1 for r in rows if r.get("artwork_url"))
    print(f"track_master.csv: artwork_url 更新 {updated}, 保有 {with_art}/{len(rows)}")


def main():
    logos = enrich_agency_logos()
    line_artists, line_tracks = collect_line_images()
    apple_art = collect_apple_artwork()
    yt_thumbs = collect_youtube_channel_thumbs()
    print(
        f"sources: line_artists={len(line_artists)} line_tracks={len(line_tracks)} "
        f"apple={len(apple_art)} yt_channel={len(yt_thumbs)} agencies={sum(1 for v in logos.values() if v)}"
    )
    enrich_artist_masters(line_artists, yt_thumbs)
    enrich_track_master(apple_art, line_tracks)
    print("完了。")


if __name__ == "__main__":
    main()
