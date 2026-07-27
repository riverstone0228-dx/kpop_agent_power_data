"""
LINE MUSIC「K-Pop Top 50」チャートを日次取得する。

出典エントリ: https://music.line.me/webapp/ranking-genre/mg0000000000000033
実エンドポイント: https://music.line.me/api2/chart/genre/mg0000000000000033/tracks.v1

- 認証不要JSON (Playwright不要)
- 日次・50曲
- artist_external_ids.csv (platform=line) で名寄せ
  ※同一アーティストに複数 artistId があり得るため縦持ち必須

出力:
  data/line_charts/YYYY-MM-DD.csv
  data/line_charts/summary_YYYY-MM-DD.csv

実行:
  python fetch_line_charts.py
"""

import csv
import datetime
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import build_artist_lookup, ensure_external_id_templates
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "line_charts")
GENRE_CODE = "mg0000000000000033"
API_URL = f"https://music.line.me/api2/chart/genre/{GENRE_CODE}/tracks.v1"
ENTRY_URL = f"https://music.line.me/webapp/ranking-genre/{GENRE_CODE}"

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)",
    "Accept": "application/json",
    "Referer": "https://music.line.me/",
    "Origin": "https://music.line.me",
}


def parse_chart_date(raw: str) -> str:
    """'2026.7.26' or '2026.07.26' -> '2026-07-26'"""
    raw = (raw or "").strip()
    if not raw:
        return datetime.date.today().isoformat()
    parts = raw.replace("/", ".").split(".")
    if len(parts) != 3:
        return datetime.date.today().isoformat()
    y, m, d = parts
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def fetch_chart():
    resp = requests.get(API_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def primary_artist(track):
    artists = track.get("artists") or []
    if not artists:
        return "", ""
    a = artists[0]
    return str(a.get("artistId", "")).strip(), a.get("artistName", "")


def main():
    ensure_external_id_templates()
    artist_lookup = build_artist_lookup("line")
    master_by_name = {r["artist_name_en"]: r for r in load_all_artists()}
    if not artist_lookup:
        print("[WARN] line の外部IDが未登録です。生データ取得は続行します。")
        print("       mine_chart_ids.py 実行後に再突合してください。")

    payload = fetch_chart()
    chart = payload.get("response", {}).get("result", {}).get("chart", {})
    tracks = (chart.get("items") or {}).get("tracks") or []
    chart_date = parse_chart_date(chart.get("chartDate", ""))
    today = datetime.date.today().isoformat()

    print(
        f"LINE MUSIC: {len(tracks)}件取得 "
        f"(title={chart.get('title')}, chartDate={chart.get('chartDate')})"
    )

    rows = []
    for track in tracks:
        line_artist_id, artist_name_local = primary_artist(track)
        ext = artist_lookup.get(line_artist_id)
        name_master = (ext or {}).get("artist_name_en", "")
        master = master_by_name.get(name_master) if name_master else None
        rank_info = track.get("rank") or {}
        rows.append(
            {
                "date": today,
                "chart_date": chart_date,
                "rank": rank_info.get("currentRank", ""),
                "rank_variation": rank_info.get("rankVariation", ""),
                "is_new": "1" if rank_info.get("isNew") else "0",
                "track_name": track.get("trackTitle", ""),
                "artist_name_local": artist_name_local,
                "line_artist_id": line_artist_id,
                "line_track_id": str(track.get("trackId", "")).strip(),
                "score": rank_info.get("score", ""),
                "listened_count": track.get("listenedCount", ""),
                "like_count": track.get("likeCount", ""),
                "agency": (master or {}).get("agency", ""),
                "sub_agency": (master or {}).get("sub_agency", ""),
                "artist_name_master": name_master,
                "match_status": (ext or {}).get("match_status", ""),
                "source_entry_url": ENTRY_URL,
            }
        )

    if not rows:
        print("チャートを1件も取得できませんでした。処理を中止します。")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    raw_path = os.path.join(OUT_DIR, f"{today}.csv")
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n生データ: {raw_path} ({len(rows)}行)")

    summary = {}
    for r in rows:
        agency = r["agency"] or "(未登録)"
        summary[agency] = summary.get(agency, 0) + 1

    summary_path = os.path.join(OUT_DIR, f"summary_{today}.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "chart_date", "agency", "charted_tracks", "chart_size", "share_pct"])
        total = len(rows)
        for agency, count in sorted(summary.items()):
            share = round(count / total * 100, 1) if total else 0
            w.writerow([today, chart_date, agency, count, total, share])
    print(f"集計:   {summary_path}")

    print("\n--- 事務所別ランクイン ---")
    for agency, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {agency}: {count}曲")


if __name__ == "__main__":
    main()
