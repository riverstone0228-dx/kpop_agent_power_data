"""
公式チャンネルから動画単位の再生・いいね・コメントを取得する。

取得対象 (アーティストごと):
  1. recent      … リリース直近10本 (uploads プレイリスト)
  2. top_views   … 累積再生数 TOP10 (search.list order=viewCount / 100u)
  3. hot_mv      … 直近で人気のある MV 努力 TOP10
                   uploads 直近50本を候補に、音楽カテゴリ寄り・10分以下・
                   勢い(再生/日齢)でランク (search 追加なし / クォータ軽)

注意:
  - search.list は 100 ユニット/回。hot_mv は追加 search を使わない。
  - 「公式MV」完全判定は API にないため title / category / duration のヒューリスティック。
  - likeCount / commentCount は投稿者設定で非公開の場合がある。

出力:
  data/youtube_videos/YYYY-MM-DD.csv
  selection 列: recent | top_views | hot_mv

MERGE キー (Databricks): date + video_id + selection
"""

from __future__ import annotations

import csv
import datetime
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from master_data import load_all_artists

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "youtube_videos")
API = "https://www.googleapis.com/youtube/v3"

# hot_mv 用
HOT_MV_CANDIDATE_N = 50          # uploads から候補に取る本数
HOT_MV_TOP_N = 10
HOT_MV_MAX_DURATION_SEC = 10 * 60  # 10分以下
MUSIC_CATEGORY_ID = "10"

# title 優遇 / 除外 (MV っぽさヒューリスティック)
MV_TITLE_BONUS = re.compile(
    r"(m/?v|music\s*video|official\s*(mv|video|audio)?|뮤직\s*비디오|공식)",
    re.I,
)
EXCLUDE_TITLE = re.compile(
    r"("
    r"live|concert|tour|behind\s*the\s*scenes|making|interview|vlog|"
    r"episode|ep\.?\s*\d|radio|podcast|reaction|highlights?|"
    r"full\s*album|dance\s*practice|choreography\s*practice|"
    r"scheduled|countdown|unboxing|fan\s*cam|직캠"
    r")",
    re.I,
)

FIELDNAMES = [
    "date",
    "agency",
    "sub_agency",
    "artist_name",
    "youtube_channel_id",
    "selection",
    "rank",
    "video_id",
    "title",
    "url",
    "published_at",
    "view_count",
    "like_count",
    "comment_count",
    "thumbnail_url",
    "duration_sec",
    "category_id",
]


def _get(path, params):
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY 未設定")
    params = {**params, "key": YOUTUBE_API_KEY}
    resp = requests.get(f"{API}/{path}", params=params, timeout=20)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube API {path} HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def parse_duration_sec(iso: str) -> int | None:
    """ISO 8601 duration (PT#H#M#S) → 秒。"""
    if not iso:
        return None
    m = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        iso.strip(),
    )
    if not m:
        return None
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def get_uploads_playlist_ids(channel_ids: list[str]) -> dict[str, str]:
    """channel_id -> uploads playlist id"""
    out = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        data = _get(
            "channels",
            {"part": "contentDetails", "id": ",".join(batch)},
        )
        for item in data.get("items", []):
            uploads = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            if uploads:
                out[item["id"]] = uploads
        time.sleep(0.05)
    return out


def get_recent_video_ids(uploads_playlist_id: str, max_results: int = 10) -> list[dict]:
    """直近アップロード。戻り値: [{video_id, published_at, title_hint}]"""
    data = _get(
        "playlistItems",
        {
            "part": "contentDetails,snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(max(max_results, 1), 50),
        },
    )
    rows = []
    for it in data.get("items", []):
        vid = it.get("contentDetails", {}).get("videoId", "")
        if not vid:
            continue
        rows.append(
            {
                "video_id": vid,
                "published_at": (it.get("contentDetails", {}).get("videoPublishedAt") or "")[:10],
                "title_hint": it.get("snippet", {}).get("title", ""),
            }
        )
    return rows


def get_top_video_ids(channel_id: str, max_results: int = 10) -> list[dict]:
    """累積再生数順 TOP。search.list = 100 units。"""
    data = _get(
        "search",
        {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
            # 可能な範囲で音楽寄り (まだ filter は後段 videos.list で厳密化可能)
            "videoCategoryId": MUSIC_CATEGORY_ID,
        },
    )
    rows = []
    for it in data.get("items", []):
        vid = it.get("id", {}).get("videoId", "")
        if not vid:
            continue
        rows.append(
            {
                "video_id": vid,
                "published_at": (it.get("snippet", {}).get("publishedAt") or "")[:10],
                "title_hint": it.get("snippet", {}).get("title", ""),
            }
        )
    return rows


def get_video_details(video_ids: list[str]) -> dict[str, dict]:
    """videos.list: statistics + snippet + contentDetails。最大50件/回。"""
    out = {}
    unique = list(dict.fromkeys(v for v in video_ids if v))
    for i in range(0, len(unique), 50):
        batch = unique[i : i + 50]
        data = _get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
        )
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            st = item.get("statistics", {})
            cd = item.get("contentDetails", {})
            duration_sec = parse_duration_sec(cd.get("duration", ""))
            thumbs = sn.get("thumbnails") or {}
            thumb = (
                (thumbs.get("medium") or {}).get("url")
                or (thumbs.get("default") or {}).get("url")
                or ""
            )
            out[item["id"]] = {
                "title": sn.get("title", ""),
                "published_at": (sn.get("publishedAt") or "")[:10],
                "view_count": st.get("viewCount", ""),
                "like_count": st.get("likeCount", ""),
                "comment_count": st.get("commentCount", ""),
                "thumbnail_url": thumb,
                "duration_sec": duration_sec if duration_sec is not None else "",
                "category_id": sn.get("categoryId", "") or "",
            }
        time.sleep(0.05)
    return out


def _as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def score_hot_mv(detail: dict, today: datetime.date) -> float:
    """直近人気度: 再生 / (日齢+7)。MV title / Music category でボーナス。"""
    views = max(_as_int(detail.get("view_count")), 0)
    pub = (detail.get("published_at") or "")[:10]
    age_days = 30
    if pub:
        try:
            age_days = max((today - datetime.date.fromisoformat(pub)).days, 0)
        except ValueError:
            pass
    base = views / (age_days + 7)

    title = detail.get("title") or ""
    if MV_TITLE_BONUS.search(title):
        base *= 1.35
    if detail.get("category_id") == MUSIC_CATEGORY_ID:
        base *= 1.15
    return base


def pick_hot_mvs(
    candidate_ids: list[str],
    details: dict[str, dict],
    today: datetime.date,
    top_n: int = HOT_MV_TOP_N,
) -> list[str]:
    """候補 ID から hot_mv 条件を満たす video_id を勢い順に top_n。"""
    scored: list[tuple[float, int, str]] = []
    for i, vid in enumerate(candidate_ids):
        d = details.get(vid)
        if not d:
            continue
        dur = d.get("duration_sec")
        if dur == "" or dur is None:
            continue
        try:
            dur_i = int(dur)
        except (TypeError, ValueError):
            continue
        if dur_i <= 0 or dur_i > HOT_MV_MAX_DURATION_SEC:
            continue

        title = d.get("title") or ""
        if EXCLUDE_TITLE.search(title):
            continue

        # 音楽カテゴリ優先: カテゴリが判明していても 10 以外は落とす
        # (カテゴリ未設定や違うが MV っぽいタイトルは通す)
        cat = d.get("category_id") or ""
        if cat and cat != MUSIC_CATEGORY_ID and not MV_TITLE_BONUS.search(title):
            continue

        sc = score_hot_mv(d, today)
        scored.append((sc, -i, vid))  # 同点時は新しい方

    scored.sort(reverse=True)
    return [vid for _, _, vid in scored[:top_n]]


def fetch_all(recent_n: int = 10, top_n: int = 10, hot_mv_n: int = HOT_MV_TOP_N) -> list[dict]:
    artists = [
        r
        for r in load_all_artists()
        if r.get("youtube_channel_id", "").strip()
        and not r["artist_name_en"].startswith("(")
    ]
    channel_ids = [r["youtube_channel_id"].strip() for r in artists]
    uploads = get_uploads_playlist_ids(channel_ids)
    today_d = datetime.date.today()
    today = today_d.isoformat()

    # 1パス目: すべての video_id を集め、一括 videos.list
    pending: list[dict] = []
    all_ids: list[str] = []
    hot_pools: dict[str, list[str]] = {}  # channel_id -> candidate video ids

    for artist in artists:
        cid = artist["youtube_channel_id"].strip()
        name = artist["artist_name_en"]
        agency = artist["agency"]
        sub = artist.get("sub_agency", "")
        base = {
            "date": today,
            "agency": agency,
            "sub_agency": sub,
            "artist_name": name,
            "youtube_channel_id": cid,
        }

        # uploads 直近 (hot_mv 用に多め。recent はその先頭)
        pl = uploads.get(cid)
        recent_pool: list[dict] = []
        if pl:
            try:
                recent_pool = get_recent_video_ids(pl, max(HOT_MV_CANDIDATE_N, recent_n))
            except Exception as e:
                print(f"[WARN] recent/hot_mv pool {name}: {e}")
        else:
            print(f"[WARN] uploads playlist なし: {name}")

        # 1) recent 10
        for rank, v in enumerate(recent_pool[:recent_n], start=1):
            pending.append({**base, "selection": "recent", "rank": rank, "video_id": v["video_id"]})
            all_ids.append(v["video_id"])

        # 2) top_views 10 (search + category music 指定)
        try:
            top = get_top_video_ids(cid, top_n)
            time.sleep(0.1)
        except Exception as e:
            # videoCategoryId 指定が弾かれるチャンネルもあるので、失敗時は category 無しで再試行
            print(f"[WARN] top_views (music category) {name}: {e} — retry without category")
            try:
                data = _get(
                    "search",
                    {
                        "part": "snippet",
                        "channelId": cid,
                        "type": "video",
                        "order": "viewCount",
                        "maxResults": top_n,
                    },
                )
                top = []
                for it in data.get("items", []):
                    vid = it.get("id", {}).get("videoId", "")
                    if vid:
                        top.append(
                            {
                                "video_id": vid,
                                "published_at": (it.get("snippet", {}).get("publishedAt") or "")[:10],
                                "title_hint": it.get("snippet", {}).get("title", ""),
                            }
                        )
                time.sleep(0.1)
            except Exception as e2:
                print(f"[WARN] top_views {name}: {e2}")
                top = []

        for rank, v in enumerate(top, start=1):
            pending.append({**base, "selection": "top_views", "rank": rank, "video_id": v["video_id"]})
            all_ids.append(v["video_id"])

        hot_pool_ids = [v["video_id"] for v in recent_pool]
        hot_pools[cid] = hot_pool_ids
        all_ids.extend(hot_pool_ids)

        print(f"{name}: recent_pool={len(recent_pool)} top={len(top)}")

    details = get_video_details(all_ids)

    # hot_mv 確定
    for artist in artists:
        name = artist["artist_name_en"]
        cid = artist["youtube_channel_id"].strip()
        pool = hot_pools.get(cid) or []
        if not pool:
            print(f"{name}: hot_mv=0")
            continue
        hot_ids = pick_hot_mvs(pool, details, today_d, top_n=hot_mv_n)
        base = {
            "date": today,
            "agency": artist["agency"],
            "sub_agency": artist.get("sub_agency", ""),
            "artist_name": name,
            "youtube_channel_id": cid,
        }
        for rank, vid in enumerate(hot_ids, start=1):
            pending.append({**base, "selection": "hot_mv", "rank": rank, "video_id": vid})
        print(f"{name}: hot_mv={len(hot_ids)}")

    rows = []
    for meta in pending:
        vid = meta["video_id"]
        st = details.get(vid, {})
        rows.append(
            {
                **meta,
                "title": st.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published_at": st.get("published_at", ""),
                "view_count": st.get("view_count", ""),
                "like_count": st.get("like_count", ""),
                "comment_count": st.get("comment_count", ""),
                "thumbnail_url": st.get("thumbnail_url", ""),
                "duration_sec": st.get("duration_sec", ""),
                "category_id": st.get("category_id", ""),
            }
        )
    return rows


def main():
    rows = fetch_all()
    if not rows:
        print("取得0件。YOUTUBE_API_KEY / channel_id を確認してください。")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    out_path = os.path.join(OUT_DIR, f"{today}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    # 内訳
    from collections import Counter

    c = Counter(r["selection"] for r in rows)
    print(f"\n{len(rows)}件を {out_path} に保存しました。 {dict(c)}")


if __name__ == "__main__":
    main()
