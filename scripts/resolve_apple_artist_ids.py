"""
iTunes Search API を使って、マスタCSVの apple_artist_id 空欄を埋めるための候補を検索する。

iTunes Search API は認証不要・無料。ただし公式に「1分あたり約20リクエスト」の
目安が示されているため、リクエスト間に3秒のスリープを入れている。

方針は resolve_artist_ids.py と同じ「候補を出して人が確定する」パターン。
自動で確定入力はしない (同名アーティストの誤マッチを防ぐため)。

実行:
  python resolve_apple_artist_ids.py
  → apple_candidates_report.csv が生成される
  → 目視で正しいIDを選び、artist_master.csv / other_agency_master.csv に手入力
"""

import csv
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

REPORT_CSV = os.path.join(os.path.dirname(__file__), "apple_candidates_report.csv")

HEADERS = {
    "User-Agent": "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)"
}

SLEEP_SEC = 3  # iTunes Search APIのレート制限対策 (約20req/分)


def search_artist(name, country="jp", limit=3):
    """iTunes Search APIでアーティストを検索。戻り値: list[str] (表示用文字列)"""
    resp = requests.get(
        "https://itunes.apple.com/search",
        params={
            "term": name,
            "entity": "musicArtist",
            "country": country,
            "limit": limit,
        },
        headers=HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        return [f"ERROR: HTTP {resp.status_code}"]

    # iTunes Search APIは Content-Type が text/javascript で返ることがある
    try:
        data = resp.json()
    except ValueError:
        return ["ERROR: JSONパース失敗"]

    results = data.get("results", [])
    if not results:
        return ["(該当なし)"]

    return [
        f"{r.get('artistName','?')} | {r.get('artistId','?')} | {r.get('primaryGenreName','?')}"
        for r in results
    ]


def main():
    rows = load_all_artists()
    targets = [
        r
        for r in rows
        if r["artist_name_en"].strip()
        and not r["artist_name_en"].startswith("(")
        and not (r.get("apple_artist_id") or "").strip()
    ]

    print(f"apple_artist_id未設定: {len(targets)}件")
    print(f"推定所要時間: 約{len(targets) * SLEEP_SEC * 2 / 60:.0f}分 (jp/kr両方を検索)\n")

    report_rows = []
    for i, row in enumerate(targets, start=1):
        name = row["artist_name_en"].strip()
        print(f"[{i}/{len(targets)}] 検索中: {name}")

        # 日本ストアと韓国ストアの両方で検索する
        # (K-popアーティストは韓国ストアの方が正確にヒットしやすい)
        jp_candidates = search_artist(name, country="jp")
        time.sleep(SLEEP_SEC)
        kr_candidates = search_artist(name, country="kr")
        time.sleep(SLEEP_SEC)

        report_rows.append(
            {
                "source_file": row["_source_file"],
                "agency": row["agency"],
                "artist_name_en": name,
                "jp_store_candidates": " / ".join(jp_candidates),
                "kr_store_candidates": " / ".join(kr_candidates),
            }
        )

    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "source_file",
                "agency",
                "artist_name_en",
                "jp_store_candidates",
                "kr_store_candidates",
            ],
        )
        w.writeheader()
        w.writerows(report_rows)

    print(f"\n完了: {REPORT_CSV}")
    print("候補を確認し、正しい artistId を source_file 列のマスタCSVに手入力してください。")
    print("※ artistId は国をまたいで同一なので、jp/krどちらの候補から取っても構いません。")


if __name__ == "__main__":
    main()
