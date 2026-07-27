"""
日次収集サマリーを Slack Incoming Webhook に投稿する。

環境変数:
  SLACK_WEBHOOK_URL  … 未設定なら何もしない (ローカルでも安全)
"""

from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@dataclass
class CollectionReport:
    """収集実行中に蓄積する結果。"""

    started_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps: dict[str, str] = field(default_factory=dict)  # name -> ok|fail|skip

    def mark_ok(self, name: str) -> None:
        self.steps[name] = "ok"

    def mark_fail(self, name: str, err: Exception | str) -> None:
        self.steps[name] = "fail"
        self.errors.append(f"{name}: {err}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _csv_row_count(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        lines = sum(1 for _ in f)
    return max(0, lines - 1)  # header除外


def _nonempty_col_count(path: Path, col_name: str) -> Optional[int]:
    if not path.is_file():
        return None
    import csv

    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return sum(1 for row in reader if (row.get(col_name) or "").strip())


def _latest_dated_csv(directory: Path) -> Optional[Path]:
    if not directory.is_dir():
        return None
    files = sorted(
        (p for p in directory.glob("????-??-??.csv")),
        key=lambda p: p.name,
        reverse=True,
    )
    return files[0] if files else None


def build_file_stats(today: Optional[datetime.date] = None) -> dict:
    """出力CSVの有無・件数を集計する。"""
    today = today or datetime.date.today()
    d = today.isoformat()

    raw = DATA / "raw" / f"{d}.csv"
    yt_videos = DATA / "youtube_videos" / f"{d}.csv"
    apple = DATA / "apple_charts" / f"{d}.csv"
    line = DATA / "line_charts" / f"{d}.csv"
    other = DATA / "other_agency_top15" / f"{d}.csv"
    top_songs = DATA / "song_rankings" / f"top_{d}.csv"
    hot_songs = DATA / "song_rankings" / f"hot_{d}.csv"
    sstv = _latest_dated_csv(DATA / "spaceshower_charts")

    return {
        "raw_rows": _csv_row_count(raw),
        "youtube_filled": _nonempty_col_count(raw, "youtube_subscribers"),
        "wiki_ja_filled": _nonempty_col_count(raw, "wikipedia_pv_ja"),
        "wiki_en_filled": _nonempty_col_count(raw, "wikipedia_pv_en"),
        "youtube_video_rows": _csv_row_count(yt_videos),
        "apple_rows": _csv_row_count(apple),
        "line_rows": _csv_row_count(line),
        "other_rows": _csv_row_count(other),
        "top_song_rows": _csv_row_count(top_songs),
        "hot_song_rows": _csv_row_count(hot_songs),
        "spaceshower_file": sstv.name if sstv else None,
        "spaceshower_rows": _csv_row_count(sstv) if sstv else None,
        "date": d,
    }


def _fmt_count(n: Optional[int], unit: str = "件") -> str:
    if n is None:
        return "なし"
    return f"{n}{unit}"


def format_message(
    report: CollectionReport,
    stats: Optional[dict] = None,
    *,
    run_url: str = "",
) -> str:
    stats = stats or build_file_stats()
    has_error = bool(report.errors)
    status = "失敗あり" if has_error else "成功"
    icon = "x" if has_error else "white_check_mark"

    lines = [
        f":{icon}: *日次 K-pop データ収集 — {status}*",
        f"日付: `{stats['date']}` (UTC {report.started_at.strftime('%Y-%m-%d %H:%M')})",
        "",
        "*出力ファイル*",
        f"• Artist snapshot (`data/raw/`): {_fmt_count(stats['raw_rows'])}"
        f" / YT埋まり {_fmt_count(stats['youtube_filled'])}"
        f" / Wiki ja {_fmt_count(stats['wiki_ja_filled'])}"
        f" / en {_fmt_count(stats['wiki_en_filled'])}",
        f"• YouTube videos: {_fmt_count(stats.get('youtube_video_rows'))}",
        f"• TOP/HOT SONG20: {_fmt_count(stats.get('top_song_rows'))}"
        f" / {_fmt_count(stats.get('hot_song_rows'))}",
        f"• Apple charts: {_fmt_count(stats['apple_rows'])}",
        f"• LINE MUSIC: {_fmt_count(stats['line_rows'])}",
        f"• Space Shower: {_fmt_count(stats['spaceshower_rows'])}"
        + (f" (`{stats['spaceshower_file']}`)" if stats.get("spaceshower_file") else ""),
        f"• OTHER TOP15: {_fmt_count(stats['other_rows'])}",
    ]

    if report.steps:
        lines.append("")
        lines.append("*ステップ*")
        for name, st in report.steps.items():
            mark = {"ok": ":large_green_circle:", "fail": ":red_circle:", "skip": ":white_circle:"}.get(
                st, ":grey_question:"
            )
            lines.append(f"{mark} {name}")

    if report.errors:
        lines.append("")
        lines.append("*エラー*")
        for e in report.errors[:15]:
            lines.append(f"• `{e}`")
        if len(report.errors) > 15:
            lines.append(f"• …他 {len(report.errors) - 15}件")

    if report.warnings:
        lines.append("")
        lines.append("*警告*")
        for w in report.warnings[:10]:
            lines.append(f"• {w}")
        if len(report.warnings) > 10:
            lines.append(f"• …他 {len(report.warnings) - 10}件")

    # 空収集の検知
    empty_signals = []
    if stats["raw_rows"] in (None, 0):
        empty_signals.append("artist snapshot")
    if stats["apple_rows"] in (None, 0):
        empty_signals.append("Apple")
    if stats["line_rows"] in (None, 0):
        empty_signals.append("LINE")
    if stats.get("youtube_filled") == 0 and (stats.get("raw_rows") or 0) > 0:
        empty_signals.append("YouTube列が全て空 (APIキー未設定の可能性)")

    if empty_signals:
        lines.append("")
        lines.append("*空/欠損の疑い*: " + ", ".join(empty_signals))

    if run_url:
        lines.append("")
        lines.append(f"<{run_url}|GitHub Actions ログ>")

    return "\n".join(lines)


def post_slack(text: str, webhook_url: Optional[str] = None) -> bool:
    """Webhook に投稿。未設定なら False を返してスキップ。"""
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        print("[INFO] SLACK_WEBHOOK_URL 未設定のため通知をスキップします。")
        return False

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                print(f"[WARN] Slack通知失敗: HTTP {resp.status} {body}")
                return False
    except urllib.error.URLError as e:
        print(f"[WARN] Slack通知失敗: {e}")
        return False

    print("[INFO] Slack に通知しました。")
    return True


def notify_collection(report: CollectionReport) -> bool:
    run_url = ""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        run_url = f"{server}/{repo}/actions/runs/{run_id}"

    text = format_message(report, run_url=run_url)
    print("\n--- Slack通知プレビュー ---\n" + text + "\n--------------------------\n")
    return post_slack(text)


def notify_job_failure(reason: str = "workflow step failed") -> bool:
    """Python収集より前に落ちた場合用の簡易通知。"""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else ""

    lines = [
        ":x: *日次 K-pop データ収集 — ジョブ失敗*",
        f"理由: `{reason}`",
    ]
    if run_url:
        lines.append(f"<{run_url}|GitHub Actions ログ>")
    return post_slack("\n".join(lines))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--failure":
        reason = sys.argv[2] if len(sys.argv) > 2 else "workflow failed"
        ok = notify_job_failure(reason)
        sys.exit(0 if ok or not os.environ.get("SLACK_WEBHOOK_URL") else 1)

    # ドライラン: 現在の data/ からサマリーだけ表示
    r = CollectionReport()
    r.mark_ok("(dry-run)")
    notify_collection(r)
