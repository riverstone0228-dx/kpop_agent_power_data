"""
Databricks Workspace Git folder を main に更新する。

CLI の既定 60s タイムアウトを避け、REST API で最大5分待つ。
環境変数:
  DATABRICKS_HOST
  DATABRICKS_TOKEN
  DATABRICKS_REPO_PATH
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def req(method: str, url: str, token: str, body=None, timeout: int = 300):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def resolve_repo_id(host: str, token: str, path: str) -> int:
    qs = urllib.parse.urlencode({"path_prefix": path})
    repos = req("GET", f"{host}/api/2.0/repos?{qs}", token, timeout=60)
    items = repos.get("repos") or []
    for r in items:
        if (r.get("path") or "").rstrip("/") == path:
            return int(r["id"])
    for r in items:
        if path in (r.get("path") or ""):
            return int(r["id"])
    raise RuntimeError(f"repo not found for path={path}: {json.dumps(repos, ensure_ascii=False)[:2000]}")


def pull_once(host: str, token: str, path: str) -> dict:
    repo_id = resolve_repo_id(host, token, path)
    print(f"Resolved repo_id={repo_id}")
    updated = req(
        "PATCH",
        f"{host}/api/2.0/repos/{repo_id}",
        token,
        body={"branch": "main"},
        timeout=300,
    )
    print(json.dumps(updated, ensure_ascii=False))
    return updated


def main() -> int:
    host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    path = os.environ.get("DATABRICKS_REPO_PATH", "").strip().rstrip("/")
    if not host or not token or not path:
        print("DATABRICKS_HOST / TOKEN / REPO_PATH required", file=sys.stderr)
        return 2

    print(f"Pulling Git folder: {path}")
    max_attempts = int(os.environ.get("DATABRICKS_PULL_RETRIES", "4"))
    for attempt in range(1, max_attempts + 1):
        print(f"=== Git folder pull attempt {attempt}/{max_attempts} ===")
        try:
            pull_once(host, token, path)
            print("Git folder pull succeeded")
            return 0
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {body}", file=sys.stderr)
        except Exception as e:
            print(f"Pull failed: {e}", file=sys.stderr)

        if attempt == max_attempts:
            break
        sleep_s = attempt * 45
        print(f"Retrying in {sleep_s}s...")
        time.sleep(sleep_s)

    print(f"Git folder pull failed after {max_attempts} attempts", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
