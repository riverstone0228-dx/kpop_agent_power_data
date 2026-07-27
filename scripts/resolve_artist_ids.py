"""
artist_master.csv の youtube_channel_id が空欄の行について、
YouTube Data API で候補を検索し、レビュー用レポートを出力する。

方針:
  自動で確定入力はしない (誤ったチャンネルを拾うリスクがあるため)。
  candidates_report.csv に上位候補を出すので、人が目で見て正しいIDを
  artist_master.csv / other_agency_master.csv に手入力する運用とする。

実行前準備:
  pip install -r requirements.txt
  .env に YOUTUBE_API_KEY=... を設定 (このリポジトリにはコミットしない)

実行:
  python resolve_artist_ids.py
  → candidates_report.csv が生成される
"""

import csv
import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
REPORT_CSV = os.path.join(os.path.dirname(__file__), "candidates_report.csv")


def search_youtube_channels(query):
    """YouTube search.list はユニットコストが高い(100)ので呼び過ぎに注意。"""
    if not YOUTUBE_API_KEY:
        return ["ERROR: YOUTUBE_API_KEY未設定"]
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": f"{query} official",
            "type": "channel",
            "maxResults": 3,
            "key": YOUTUBE_API_KEY,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return [f"ERROR: {resp.status_code} {resp.text[:200]}"]
    items = resp.json().get("items", [])
    return [
        f"{it['snippet']['channelTitle']} | {it['snippet']['channelId']}"
        for it in items
    ]


def main():
    rows = load_all_artists()
    report_rows = []

    for row in rows:
        name = row["artist_name_en"].strip()
        if not name or name.startswith("("):
            continue
        if row.get("youtube_channel_id", "").strip():
            continue

        print(f"検索中: {name}")
        report_rows.append(
            {
                "source_file": row["_source_file"],
                "agency": row["agency"],
                "artist_name_en": name,
                "youtube_candidates": " / ".join(search_youtube_channels(name)),
            }
        )

    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_file",
                "agency",
                "artist_name_en",
                "youtube_candidates",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(
        f"\n完了: {REPORT_CSV} を確認し、正しいIDを該当するマスタCSV"
        f"(source_file列を参照)に手入力してください。"
    )


if __name__ == "__main__":
    main()
