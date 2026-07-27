"""
「他事務所TOP15」インデックスの日次リバランス。

プール方針:
  other_agency_master.csv に 20〜30組の候補を溜める。
  集計・コンテンツで見せるのはその中の TOP15 のみ。

選定ロジック (2026-07-26改定):
  1. チャート勢いスコア (主指標, 70%)
     - LINE MUSIC K-Pop Top50: 直近7日
     - スペースシャワー KOREAN HITS: 直近2週
     - Apple Music (jp/kr, K-Popジャンルのみ): 直近7日
     - 各出現で score += (chart_size - rank + 1)
       ※上位ほど加点。同一日・同一プラットフォームの複数曲は合算
  2. YouTube規模 (副指標, 30%, データがある場合のみ)
     - log1p(youtube_subscribers) をプール内で0-1正規化
     - 登録者データが無い場合はチャート勢い100%で順位付け
  3. ヒステリシス (入れ替えノイズ抑制)
     - 前日TOP15にいたアーティストは、当日順位が17位以下に落ちたときだけ除外
     - 新規は当日14位以内、または15位かつ空きがある場合のみ採用
     - → 境界付近の日次チラつきを防ぎ、週次の「リバランス」感を出す

出力:
  data/other_agency_top15/YYYY-MM-DD.csv
  data/other_agency_top15/changelog_YYYY-MM-DD.txt

実行:
  python rank_other_agency_top15.py
  python rank_other_agency_top15.py 2026-07-26
"""

import csv
import datetime
import glob
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "other_agency_top15")
LINE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "line_charts")
SSTV_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "spaceshower_charts")
APPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "apple_charts")

TOP_N = 15
ENTER_RANK = 14          # この順位以内なら新規採用可
DROP_RANK = 17           # この順位より下で既存メンバー除外
LINE_LOOKBACK_DAYS = 7
APPLE_LOOKBACK_DAYS = 7
SSTV_LOOKBACK_WEEKS = 2  # ファイル数ベースで直近N件
CHART_WEIGHT = 0.70
YT_WEIGHT = 0.30


def parse_date(s):
    return datetime.date.fromisoformat(s)


def load_other_pool():
    """OTHERマスタの artist_name_en 集合と sub_agency 辞書。"""
    pool = {}
    for row in load_all_artists():
        if row.get("agency") == "OTHER":
            pool[row["artist_name_en"]] = row
    return pool


def load_raw_by_date(date_str):
    path = os.path.join(RAW_DIR, f"{date_str}.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["artist_name"]: r for r in csv.DictReader(f) if r.get("agency") == "OTHER"}


def previous_top15(before_date_str):
    files = sorted(glob.glob(os.path.join(OUT_DIR, "[0-9]*.csv")))
    files = [
        f
        for f in files
        if not os.path.basename(f).startswith("changelog_")
        and os.path.basename(f).replace(".csv", "") < before_date_str
    ]
    if not files:
        return []
    with open(files[-1], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def iter_chart_files(directory, lookback_dates=None, max_files=None):
    """YYYY-MM-DD.csv のみ (summary除外)。新しい順。"""
    files = sorted(
        [
            p
            for p in glob.glob(os.path.join(directory, "[0-9][0-9][0-9][0-9]-*.csv"))
            if not os.path.basename(p).startswith("summary_")
        ],
        reverse=True,
    )
    if lookback_dates is not None:
        files = [p for p in files if os.path.basename(p).replace(".csv", "") in lookback_dates]
    if max_files is not None:
        files = files[:max_files]
    return files


def add_rank_points(score_map, artist_name, rank, chart_size):
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return
    points = max(chart_size - rank + 1, 1)
    score_map[artist_name] += points


def chart_momentum(pool_names, as_of: datetime.date):
    """プール内アーティストのチャート勢いスコア。"""
    scores = defaultdict(float)
    platforms_hit = defaultdict(set)

    # LINE: 直近N日
    line_dates = {
        (as_of - datetime.timedelta(days=i)).isoformat() for i in range(LINE_LOOKBACK_DAYS)
    }
    for path in iter_chart_files(LINE_DIR, lookback_dates=line_dates):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        size = len(rows) or 50
        for r in rows:
            name = (r.get("artist_name_master") or "").strip()
            if name in pool_names:
                add_rank_points(scores, name, r.get("rank"), size)
                platforms_hit[name].add("line")

    # SSTV: 直近N週分のファイル
    for path in iter_chart_files(SSTV_DIR, max_files=SSTV_LOOKBACK_WEEKS):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        size = len(rows) or 40
        for r in rows:
            name = (r.get("artist_name_master") or "").strip()
            if name in pool_names:
                add_rank_points(scores, name, r.get("rank"), size)
                platforms_hit[name].add("spaceshower")

    # Apple jp/kr: 直近N日・K-Popのみ
    apple_dates = {
        (as_of - datetime.timedelta(days=i)).isoformat() for i in range(APPLE_LOOKBACK_DAYS)
    }
    for path in iter_chart_files(APPLE_DIR, lookback_dates=apple_dates):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # 国別にchart_sizeを数える
        by_country = defaultdict(list)
        for r in rows:
            if r.get("country") not in ("jp", "kr"):
                continue
            if r.get("is_kpop_genre") != "1" and not r.get("agency"):
                # K-pop判定なし＆マスタ未一致は除外
                continue
            # マスタ一致のOTHER、またはK-popジャンル
            name = (r.get("artist_name_master") or "").strip()
            if name in pool_names:
                by_country[r["country"]].append(r)
        for country, country_rows in by_country.items():
            # その日の国別総行数をchart_size近似に使う
            all_country = [r for r in rows if r.get("country") == country]
            size = len(all_country) or 100
            for r in country_rows:
                name = (r.get("artist_name_master") or "").strip()
                add_rank_points(scores, name, r.get("rank"), size)
                platforms_hit[name].add(f"apple_{country}")

    return scores, platforms_hit


def normalize(values):
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def composite_scores(pool, as_of_str):
    as_of = parse_date(as_of_str)
    pool_names = set(pool.keys())
    momentum, platforms_hit = chart_momentum(pool_names, as_of)

    raw = load_raw_by_date(as_of_str)
    yt = {}
    for name in pool_names:
        try:
            yt[name] = math.log1p(float((raw.get(name) or {}).get("youtube_subscribers") or 0))
        except ValueError:
            yt[name] = 0.0

    has_yt = any(v > 0 for v in yt.values())
    mom_n = normalize({n: momentum.get(n, 0.0) for n in pool_names})
    yt_n = normalize(yt) if has_yt else {n: 0.0 for n in pool_names}

    results = []
    for name, row in pool.items():
        chart_score = mom_n.get(name, 0.0)
        yt_score = yt_n.get(name, 0.0)
        if has_yt:
            total = CHART_WEIGHT * chart_score + YT_WEIGHT * yt_score
        else:
            total = chart_score
        results.append(
            {
                "artist_name": name,
                "sub_agency": row.get("sub_agency", ""),
                "chart_momentum_raw": round(momentum.get(name, 0.0), 1),
                "chart_momentum_norm": round(chart_score, 4),
                "youtube_subs_norm": round(yt_score, 4) if has_yt else "",
                "platforms_hit": len(platforms_hit.get(name, set())),
                "score": round(total, 6),
                "youtube_subscribers": (raw.get(name) or {}).get("youtube_subscribers", ""),
            }
        )

    # score降順、同点はplatforms_hit、さらに名前
    results.sort(key=lambda r: (-r["score"], -r["platforms_hit"], r["artist_name"]))
    return results, has_yt


def apply_hysteresis(ranked, prev_top_names):
    """
    ranked: score順の全プール。
    戻り値: TOP15リスト (ヒステリシス適用後)。
    """
    rank_of = {r["artist_name"]: i + 1 for i, r in enumerate(ranked)}
    by_name = {r["artist_name"]: r for r in ranked}

    # 1) 既存メンバーで DROP_RANK より上に残っている人を優先確保
    kept = []
    for name in prev_top_names:
        rnk = rank_of.get(name)
        if rnk is not None and rnk <= DROP_RANK:
            kept.append(name)

    # 2) 空きを当日上位から埋める (ENTER_RANK以内、または枠が余れば15位まで)
    for r in ranked:
        if len(kept) >= TOP_N:
            break
        name = r["artist_name"]
        if name in kept:
            continue
        rnk = rank_of[name]
        slots_left = TOP_N - len(kept)
        if rnk <= ENTER_RANK or (rnk <= TOP_N and slots_left > 0 and name not in prev_top_names):
            # 新規は ENTER_RANK 以内のみ。枠が余って既存が少ない初日は TOP_N まで取る
            if not prev_top_names:
                kept.append(name)
            elif rnk <= ENTER_RANK:
                kept.append(name)
            elif slots_left > 0 and rnk <= TOP_N and len(kept) < TOP_N:
                # 既存がDROPで減った穴埋め: TOP_N以内なら可
                kept.append(name)

    # 初日や既存が少ない場合の埋め
    if len(kept) < TOP_N:
        for r in ranked:
            if len(kept) >= TOP_N:
                break
            if r["artist_name"] not in kept:
                kept.append(r["artist_name"])

    return [by_name[n] for n in kept[:TOP_N]]


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    pool = load_other_pool()
    if not pool:
        print("OTHERプールが空です。")
        return

    ranked, has_yt = composite_scores(pool, date_str)
    prev_rows = previous_top15(date_str)
    prev_names = [r["artist_name"] for r in prev_rows]

    top15 = apply_hysteresis(ranked, prev_names)
    # 表示用に score 順で再ソート
    top15.sort(key=lambda r: (-r["score"], -r["platforms_hit"], r["artist_name"]))

    current_names = {r["artist_name"] for r in top15}
    prev_set = set(prev_names)
    entered = current_names - prev_set
    dropped = prev_set - current_names

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{date_str}.csv")
    fields = [
        "rank",
        "artist_name",
        "sub_agency",
        "score",
        "chart_momentum_raw",
        "chart_momentum_norm",
        "youtube_subs_norm",
        "platforms_hit",
        "youtube_subscribers",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(top15, start=1):
            row = {"rank": i, **{k: r.get(k, "") for k in fields if k != "rank"}}
            w.writerow(row)

    log_path = os.path.join(OUT_DIR, f"changelog_{date_str}.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"OTHER TOP15 rebalance {date_str}\n")
        f.write(f"pool_size={len(pool)} has_youtube={has_yt}\n")
        f.write(f"weights: chart={CHART_WEIGHT} youtube={YT_WEIGHT if has_yt else 0}\n")
        f.write(f"hysteresis: enter<={ENTER_RANK} drop>={DROP_RANK}\n")
        if entered:
            f.write(f"entered: {', '.join(sorted(entered))}\n")
        if dropped:
            f.write(f"dropped: {', '.join(sorted(dropped))}\n")
        if not entered and not dropped:
            f.write("no membership changes\n")

    print(f"プール {len(pool)}組 → TOP15 を {out_path} に保存")
    print(f"指標: チャート勢い{' + YouTube規模' if has_yt else 'のみ'} / ヒステリシスあり")
    for i, r in enumerate(top15, start=1):
        print(
            f"  {i:2d}. {r['artist_name']:20s} score={r['score']:.4f} "
            f"chart={r['chart_momentum_raw']} platforms={r['platforms_hit']}"
        )
    if entered:
        print(f"新規ランクイン: {', '.join(sorted(entered))}")
    if dropped:
        print(f"ランク外に: {', '.join(sorted(dropped))}")


if __name__ == "__main__":
    main()
