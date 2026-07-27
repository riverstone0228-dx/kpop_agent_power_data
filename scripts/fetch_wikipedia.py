"""
Wikipedia Pageviews API からページビュー数を取得する。
認証不要・完全無料。artist_master.csv の wikipedia_title_ja / wikipedia_title_en を使う。

デフォルトは「一昨日」分 (APIは直近1〜2日分が未公開のことが多い)。

実行:
  python fetch_wikipedia.py            # 一昨日分を取得しCSV出力
  python fetch_wikipedia.py 2026-07-24 # 日付指定
"""

import os
import sys
import time
import datetime
import urllib.parse
import requests

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

HEADERS = {
    # Wikimedia API は User-Agent 必須 (連絡先を入れるのが推奨)
    "User-Agent": "riverstone-kpop-power-index/0.1 (riverstone0228@gmail.com)"
}


def get_pageviews(title, lang, date):
    """1記事・1言語・1日分のPVを取得。存在しない場合はNoneを返す。"""
    if not title:
        return None
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    date_str = date.strftime("%Y%m%d")
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia/all-access/all-agents/{encoded}/daily/{date_str}/{date_str}"
    )
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return items[0]["views"] if items else None


def main():
    target_date = (
        datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        if len(sys.argv) > 1
        else datetime.date.today() - datetime.timedelta(days=2)
    )

    rows = load_all_artists()

    results = []
    not_found = []

    for row in rows:
        name = row["artist_name_en"]
        title_ja = row.get("wikipedia_title_ja", "").strip()
        title_en = row.get("wikipedia_title_en", "").strip()

        pv_ja = get_pageviews(title_ja, "ja", target_date)
        time.sleep(0.1)
        pv_en = get_pageviews(title_en, "en", target_date)
        time.sleep(0.1)

        if pv_ja is None:
            not_found.append(f"{name} (ja: {title_ja})")
        if pv_en is None:
            not_found.append(f"{name} (en: {title_en})")

        results.append(
            {
                "date": target_date.isoformat(),
                "agency": row["agency"],
                "artist_name": name,
                "wikipedia_pv_ja": pv_ja if pv_ja is not None else "",
                "wikipedia_pv_en": pv_en if pv_en is not None else "",
            }
        )
        print(f"{name}: ja={pv_ja} en={pv_en}")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"wikipedia_{target_date.isoformat()}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "agency", "artist_name", "wikipedia_pv_ja", "wikipedia_pv_en"],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\n保存先: {out_path}")
    if not_found:
        print(f"\n記事タイトルが見つからなかった項目 ({len(not_found)}件) — artist_master.csvの表記を要修正:")
        for item in not_found:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
