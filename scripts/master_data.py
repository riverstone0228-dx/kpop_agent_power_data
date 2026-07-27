"""
複数のマスタCSV(4大事務所 + 他事務所候補プール)をまとめて読み込む共通モジュール。
新しいマスタファイルを追加したい場合は MASTER_FILES にパスを足すだけでよい。
"""

import csv
import os

SCRIPTS_DIR = os.path.dirname(__file__)

MASTER_FILES = [
    os.path.join(SCRIPTS_DIR, "artist_master.csv"),          # 4大事務所 (HYBE/JYP/YG/SM)
    os.path.join(SCRIPTS_DIR, "other_agency_master.csv"),    # 他事務所TOP15候補プール
]


def load_all_artists():
    """全マスタファイルを結合して1つのlist[dict]として返す。各行に _source_file を付与。"""
    rows = []
    for path in MASTER_FILES:
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["_source_file"] = os.path.basename(path)
                rows.append(row)
    return rows
