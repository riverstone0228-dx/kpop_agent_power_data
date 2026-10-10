"""
アーティストパワー / 事務所パワーの日次計算 (v2, 2026-10-10)。

アーティストパワー (0〜100):
  勢い   40%  直近7日の YouTube チャンネル再生増 (75%) + Wikipedia 直近7日PV ja+en (25%)
  楽曲   30%  直近7日のチャート加点 (LINE / Apple jp·kr / Space Shower 直近2週)
  規模   20%  YouTube 登録者数
  好き度 10%  直近動画 (recent / hot_mv) のいいね率 = いいね合計 ÷ 再生合計

  各要素は「値が正のアーティストの中でのパーセンタイル」(0〜1)。値 0・データ無しは 0 点。
  ただし好き度は再生が少ない/いいね非公開だと算出できないため、無い場合は残り3要素で按分する。
  勢いの内訳 (YouTube / Wikipedia) も片方しか無ければもう片方だけで評価する。

事務所パワー:
  HYBE / JYP / YG / SM … 所属アーティストのパワー合計
  OTHER                … その日の OTHER TOP15 メンバーの合計

出力:
  data/power/artists_YYYY-MM-DD.csv
  data/power/agencies_YYYY-MM-DD.csv

実行:
  python compute_power.py              # data/raw の最新日
  python compute_power.py 2026-10-10
  python compute_power.py --backfill   # data/raw の全日付を再計算
"""

from __future__ import annotations

import argparse
import csv
import datetime
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from rank_other_agency_top15 import chart_momentum

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
YT_DIR = os.path.join(DATA_DIR, "youtube_videos")
TOP15_DIR = os.path.join(DATA_DIR, "other_agency_top15")
OUT_DIR = os.path.join(DATA_DIR, "power")

WEIGHTS = {"momentum": 0.40, "songs": 0.30, "scale": 0.20, "affinity": 0.10}
MOMENTUM_YT_SHARE = 0.75
WIKI_LOOKBACK_DAYS = 13          # Wikipedia は週1回(月曜)なので直近2週以内の最新値を使う
AFFINITY_MIN_VIEWS = 50_000      # これ未満の再生合計ではいいね率がブレるので算出しない
AFFINITY_SELECTIONS = ("recent", "hot_mv")
MAJOR_AGENCIES = ("HYBE", "JYP", "YG", "SM")

ARTIST_FIELDS = [
    "date", "rank", "agency", "sub_agency", "artist_name", "power",
    "momentum_score", "songs_score", "scale_score", "affinity_score",
    "yt_views_7d", "wiki_pv_7d", "chart_points_7d", "youtube_subscribers", "like_rate",
    "power_7d_ago", "rank_7d_ago", "rank_change_7d",
]
AGENCY_FIELDS = [
    "date", "rank", "agency", "power", "artists", "avg_power", "top_artist",
    "power_7d_ago", "power_change_7d",
]


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def raw_dates():
    return sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(RAW_DIR, "[0-9]*.csv")))


_raw_cache: dict[str, dict] = {}


def load_raw(date_str):
    if date_str not in _raw_cache:
        rows = read_csv(os.path.join(RAW_DIR, f"{date_str}.csv"))
        _raw_cache[date_str] = {r["artist_name"]: r for r in rows if r.get("artist_name")}
    return _raw_cache[date_str]


def yt_views_7d(name, as_of: datetime.date):
    """7日前との累計再生差。7日前が無ければ窓内の最古日から7日換算する。"""
    cur = to_int((load_raw(as_of.isoformat()).get(name) or {}).get("youtube_total_views"))
    if not cur:
        return None
    for back in range(7, 0, -1):
        d = as_of - datetime.timedelta(days=back)
        prev = to_int((load_raw(d.isoformat()).get(name) or {}).get("youtube_total_views"))
        if prev:
            return max(cur - prev, 0) * 7 / back
    return None


def wiki_pv_7d(name, as_of: datetime.date):
    for back in range(0, WIKI_LOOKBACK_DAYS + 1):
        d = as_of - datetime.timedelta(days=back)
        row = load_raw(d.isoformat()).get(name) or {}
        ja, en = to_int(row.get("wikipedia_pv_ja")), to_int(row.get("wikipedia_pv_en"))
        if ja is not None or en is not None:
            return (ja or 0) + (en or 0)
    return None


def like_rates(date_str):
    seen = set()
    views, likes = defaultdict(int), defaultdict(int)
    for r in read_csv(os.path.join(YT_DIR, f"{date_str}.csv")):
        if r.get("selection") not in AFFINITY_SELECTIONS:
            continue
        vid = r.get("video_id")
        if not vid or vid in seen:
            continue
        v, l = to_int(r.get("view_count")), to_int(r.get("like_count"))
        if not v or l is None:
            continue
        seen.add(vid)
        views[r["artist_name"]] += v
        likes[r["artist_name"]] += l
    return {n: likes[n] / views[n] for n in views if views[n] >= AFFINITY_MIN_VIEWS}


def percentile_scores(values: dict):
    """正の値だけでパーセンタイル (0,1]。0 以下は 0、None は None。"""
    positives = sorted(v for v in values.values() if v is not None and v > 0)
    n = len(positives)
    out = {}
    for name, v in values.items():
        if v is None:
            out[name] = None
        elif v <= 0 or not n:
            out[name] = 0.0
        else:
            out[name] = sum(1 for p in positives if p <= v) / n
    return out


def combine(parts: dict, weights: dict):
    used = {k: w for k, w in weights.items() if parts.get(k) is not None}
    total_w = sum(used.values())
    if not total_w:
        return None
    return sum(parts[k] * w for k, w in used.items()) / total_w


def load_power(prefix, date_str):
    return read_csv(os.path.join(OUT_DIR, f"{prefix}_{date_str}.csv"))


def compute(date_str):
    as_of = datetime.date.fromisoformat(date_str)
    raw = load_raw(date_str)
    if not raw:
        print(f"skip {date_str}: data/raw が無い")
        return None

    # マスタ追加直後で raw 未収集の TOP15 メンバーも事務所合計から漏れないよう含める
    raw = dict(raw)
    for t in read_csv(os.path.join(TOP15_DIR, f"{date_str}.csv")):
        n = t.get("artist_name")
        if n and n not in raw:
            raw[n] = {"agency": "OTHER", "sub_agency": t.get("sub_agency", ""), "artist_name": n}

    names = list(raw.keys())
    momentum_points, _ = chart_momentum(set(names), as_of)
    rates = like_rates(date_str)

    yt7 = {n: yt_views_7d(n, as_of) for n in names}
    wiki7 = {n: wiki_pv_7d(n, as_of) for n in names}
    charts = {n: momentum_points.get(n, 0.0) for n in names}
    subs = {n: to_int(raw[n].get("youtube_subscribers")) for n in names}
    likes = {n: rates.get(n) for n in names}

    yt_s, wiki_s = percentile_scores(yt7), percentile_scores(wiki7)
    song_s, scale_s, aff_s = percentile_scores(charts), percentile_scores(subs), percentile_scores(likes)

    prev_date = (as_of - datetime.timedelta(days=7)).isoformat()
    prev = {r["artist_name"]: r for r in load_power("artists", prev_date)}

    rows = []
    for n in names:
        mom = combine(
            {"yt": yt_s[n], "wiki": wiki_s[n]},
            {"yt": MOMENTUM_YT_SHARE, "wiki": 1 - MOMENTUM_YT_SHARE},
        )
        parts = {
            "momentum": mom or 0.0,
            "songs": song_s[n],
            "scale": scale_s[n] or 0.0,
            "affinity": aff_s[n],
        }
        power = (combine(parts, WEIGHTS) or 0.0) * 100
        r = raw[n]
        rows.append(
            {
                "date": date_str,
                "agency": r.get("agency", "") or "OTHER",
                "sub_agency": r.get("sub_agency", ""),
                "artist_name": n,
                "power": round(power, 2),
                "momentum_score": round((mom or 0.0) * 100, 1),
                "songs_score": round(song_s[n] * 100, 1),
                "scale_score": round((scale_s[n] or 0.0) * 100, 1),
                "affinity_score": "" if aff_s[n] is None else round(aff_s[n] * 100, 1),
                "yt_views_7d": "" if yt7[n] is None else int(yt7[n]),
                "wiki_pv_7d": "" if wiki7[n] is None else wiki7[n],
                "chart_points_7d": round(charts[n], 1),
                "youtube_subscribers": subs[n] or "",
                "like_rate": "" if likes[n] is None else round(likes[n], 5),
            }
        )

    rows.sort(key=lambda x: (-x["power"], x["artist_name"]))
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
        p = prev.get(row["artist_name"])
        row["power_7d_ago"] = p["power"] if p else ""
        row["rank_7d_ago"] = p["rank"] if p else ""
        row["rank_change_7d"] = int(p["rank"]) - i if p else ""

    agencies = aggregate_agencies(rows, date_str, prev_date)
    write(f"artists_{date_str}.csv", ARTIST_FIELDS, rows)
    write(f"agencies_{date_str}.csv", AGENCY_FIELDS, agencies)
    return rows, agencies


def aggregate_agencies(rows, date_str, prev_date):
    top15 = {r["artist_name"] for r in read_csv(os.path.join(TOP15_DIR, f"{date_str}.csv"))}
    if not top15:
        others = [r for r in rows if r["agency"] == "OTHER"]
        top15 = {r["artist_name"] for r in others[:15]}

    groups = defaultdict(list)
    for r in rows:
        ag = r["agency"]
        if ag in MAJOR_AGENCIES or (ag == "OTHER" and r["artist_name"] in top15):
            groups[ag].append(r)

    prev = {r["agency"]: r for r in load_power("agencies", prev_date)}
    out = []
    for ag, members in groups.items():
        total = sum(m["power"] for m in members)
        p = prev.get(ag)
        out.append(
            {
                "date": date_str,
                "agency": ag,
                "power": round(total, 1),
                "artists": len(members),
                "avg_power": round(total / len(members), 1),
                "top_artist": max(members, key=lambda m: m["power"])["artist_name"],
                "power_7d_ago": p["power"] if p else "",
                "power_change_7d": round(total - float(p["power"]), 1) if p else "",
            }
        )
    out.sort(key=lambda x: -x["power"])
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


def write(filename, fields, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, filename), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", help="YYYY-MM-DD (省略時は data/raw の最新日)")
    parser.add_argument("--backfill", action="store_true", help="data/raw の全日付を古い順に再計算")
    args = parser.parse_args(argv)

    dates = raw_dates()
    if not dates:
        print("data/raw が空です。")
        return
    targets = dates if args.backfill else [args.date or dates[-1]]

    for d in targets:
        result = compute(d)
        if not result:
            continue
        rows, agencies = result
        if not args.backfill or d == targets[-1]:
            print(f"\n=== POWER {d} ===")
            for r in rows[:10]:
                print(
                    f"  {r['rank']:2d}. {r['artist_name']:22s} {r['agency']:6s} power={r['power']:6.2f} "
                    f"mom={r['momentum_score']} songs={r['songs_score']} scale={r['scale_score']} aff={r['affinity_score']}"
                )
            for a in agencies:
                print(f"  [{a['agency']:5s}] power={a['power']:7.1f} artists={a['artists']} avg={a['avg_power']}")
    if args.backfill:
        print(f"\nbackfill: {len(targets)} days → {OUT_DIR}")


if __name__ == "__main__":
    main()
