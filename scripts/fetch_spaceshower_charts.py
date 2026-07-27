"""
スペースシャワーTV「KOREAN HITS RANKING」の週次チャートを取得する。

出典エントリ: https://tv.spaceshower.jp/p/00089521/
実エンドポイント: https://tv.spaceshower.jp/p/chart/00089521/chart.json
履歴: https://tv.spaceshower.jp/p/chart/00089521/YYYYMMDD/chart.json

- 認証不要JSON (Playwright不要)
- 週次・40曲、HMV売上ベース
- artist_external_ids.csv (platform=spaceshower) で名寄せ

出力:
  data/spaceshower_charts/YYYY-MM-DD.csv      … 生データ (ファイル日付=放送日)
  data/spaceshower_charts/summary_YYYY-MM-DD.csv … 事務所集計

実行:
  python fetch_spaceshower_charts.py
  python fetch_spaceshower_charts.py --history 4   # 直近4週分をバックフィル
  python fetch_spaceshower_charts.py --date 20260717
"""

import argparse
import csv
import datetime
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from external_ids import build_artist_lookup, ensure_external_id_templates
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "spaceshower_charts")
PROGRAM_ID = "00089521"
CHART_URL = f"https://tv.spaceshower.jp/p/chart/{PROGRAM_ID}/chart.json"
HISTORY_URL = f"https://tv.spaceshower.jp/p/chart/{PROGRAM_ID}/{{yyyymmdd}}/chart.json"
ENTRY_URL = f"https://tv.spaceshower.jp/p/{PROGRAM_ID}/"

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)",
    "Accept": "application/json",
    "Referer": ENTRY_URL,
}


def parse_chart_date(raw: str) -> str:
    """'2026/07/24' -> '2026-07-24'"""
    raw = (raw or "").strip()
    if not raw:
        return datetime.date.today().isoformat()
    return raw.replace("/", "-")


def fetch_chart(url=None):
    resp = requests.get(url or CHART_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_history(yyyymmdd: str):
    return fetch_chart(HISTORY_URL.format(yyyymmdd=yyyymmdd))


def build_master_by_name():
    return {r["artist_name_en"]: r for r in load_all_artists()}


def rows_from_payload(payload, artist_lookup, master_by_name):
    chart_date = parse_chart_date(payload.get("date", ""))
    rows = []
    for entry in payload.get("ranking", []):
        eid = str(entry.get("artistId", "")).strip()
        ext = artist_lookup.get(eid)
        name_master = (ext or {}).get("artist_name_en", "")
        master = master_by_name.get(name_master) if name_master else None
        rows.append(
            {
                "chart_date": chart_date,
                "rank": entry.get("rank", ""),
                "track_name": entry.get("songTitle", ""),
                "artist_name_local": entry.get("artistName", ""),
                "spaceshower_artist_id": eid,
                "spaceshower_song_id": str(entry.get("songId", "")).strip(),
                "agency": (master or {}).get("agency", ""),
                "sub_agency": (master or {}).get("sub_agency", ""),
                "artist_name_master": name_master,
                "match_status": (ext or {}).get("match_status", ""),
                "source_entry_url": ENTRY_URL,
            }
        )
    return chart_date, rows, payload.get("prevHosoDate", "")


def write_outputs(chart_date, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    raw_path = os.path.join(OUT_DIR, f"{chart_date}.csv")
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"生データ: {raw_path} ({len(rows)}行)")

    summary = {}
    for r in rows:
        agency = r["agency"] or "(未登録)"
        summary[agency] = summary.get(agency, 0) + 1

    summary_path = os.path.join(OUT_DIR, f"summary_{chart_date}.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chart_date", "agency", "charted_tracks", "chart_size", "share_pct"])
        total = len(rows)
        for agency, count in sorted(summary.items()):
            share = round(count / total * 100, 1) if total else 0
            w.writerow([chart_date, agency, count, total, share])
    print(f"集計:   {summary_path}")

    print("\n--- 事務所別ランクイン ---")
    for agency, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {agency}: {count}曲")


def process_payload(payload, artist_lookup, master_by_name):
    chart_date, rows, prev = rows_from_payload(payload, artist_lookup, master_by_name)
    if not rows:
        print(f"[WARN] {chart_date}: ランキングが空です")
        return chart_date, prev
    write_outputs(chart_date, rows)
    return chart_date, prev


def yyyymmdd_from_prev(prev_path: str) -> str:
    # "/20260717/chart.json" -> "20260717"
    for part in (prev_path or "").split("/"):
        if part.isdigit() and len(part) == 8:
            return part
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="履歴日付 YYYYMMDD")
    parser.add_argument("--history", type=int, default=0, help="現在から遡って何週分取得するか")
    args = parser.parse_args()

    ensure_external_id_templates()
    artist_lookup = build_artist_lookup("spaceshower")
    master_by_name = build_master_by_name()
    if not artist_lookup:
        print("[WARN] spaceshower の外部IDが未登録です。生データ取得は続行します。")
        print("       mine_chart_ids.py 実行後に再突合してください。")

    if args.date:
        payload = fetch_history(args.date)
        process_payload(payload, artist_lookup, master_by_name)
        return

    payload = fetch_chart()
    chart_date, prev = process_payload(payload, artist_lookup, master_by_name)

    seen = {chart_date}
    for _ in range(max(0, args.history)):
        ymd = yyyymmdd_from_prev(prev)
        if not ymd:
            break
        try:
            payload = fetch_history(ymd)
        except Exception as e:
            print(f"[WARN] 履歴 {ymd} の取得失敗: {e}")
            break
        chart_date, prev = process_payload(payload, artist_lookup, master_by_name)
        if chart_date in seen:
            break
        seen.add(chart_date)


if __name__ == "__main__":
    main()
