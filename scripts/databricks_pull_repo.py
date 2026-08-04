"""
Databricks Workspace Git folder を main に更新する。

CLI の既定 60s タイムアウトを避け、REST API で最大5分待つ。
環境変数:
  DATABRICKS_HOST
  DATABRICKS_TOKEN
  DATABRICKS_REPO_PATH   … Git folder のパス（多少違ってもリポジトリURLで名寄せ）
  DATABRICKS_REPO_ID     … 任意。分かっていれば最優先（数字）
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# このリポジトリを示す GitHub URL 断片
GITHUB_URL_HINT = "github.com/riverstone0228-dx/kpop_agent_power_data"


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


def normalize_path(p: str) -> str:
    p = (p or "").strip().rstrip("/")
    # UI コピー由来の表記ゆれを吸収
    if p.startswith("/Workspace/"):
        p = p[len("/Workspace") :]
    if p.startswith("Workspace/"):
        p = "/" + p[len("Workspace/") :]
    return p


def list_repos(host: str, token: str, path_prefix: str = "") -> list[dict]:
    if path_prefix:
        qs = urllib.parse.urlencode({"path_prefix": path_prefix})
        url = f"{host}/api/2.0/repos?{qs}"
    else:
        url = f"{host}/api/2.0/repos"
    payload = req("GET", url, token, timeout=60)
    return list(payload.get("repos") or [])


def resolve_repo(host: str, token: str, path: str, repo_id_env: str = "") -> dict:
    if repo_id_env.strip().isdigit():
        rid = int(repo_id_env.strip())
        print(f"Using DATABRICKS_REPO_ID={rid}")
        return {"id": rid, "path": path}

    want = normalize_path(path)
    candidates: list[dict] = []

    # 1) path_prefix で絞り込み（prefix が違っても親を試す）
    prefixes = []
    for p in [want, "/".join(want.split("/")[:3]), "/Users", ""]:
        if p not in prefixes:
            prefixes.append(p)

    seen_ids = set()
    for pref in prefixes:
        try:
            items = list_repos(host, token, pref)
        except Exception as e:
            print(f"[WARN] list repos prefix={pref!r}: {e}", file=sys.stderr)
            continue
        for r in items:
            rid = r.get("id")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            candidates.append(r)

    if not candidates:
        raise RuntimeError("No Databricks repos returned by API")

    print("Known repos:")
    for r in candidates:
        print(f"  id={r.get('id')} path={r.get('path')} url={r.get('url')}")

    # 2) 完全一致
    for r in candidates:
        if normalize_path(r.get("path") or "") == want:
            print(f"Matched exact path: {r.get('path')}")
            return r

    # 3) 末尾一致 / 部分一致
    want_base = want.rsplit("/", 1)[-1]
    for r in candidates:
        rp = normalize_path(r.get("path") or "")
        if rp.endswith("/" + want_base) or rp.endswith(want_base):
            print(f"Matched path suffix: {rp}")
            return r
        if want in rp or rp in want:
            print(f"Matched path contains: {rp}")
            return r

    # 4) GitHub URL
    for r in candidates:
        url = (r.get("url") or "").lower()
        if GITHUB_URL_HINT.lower() in url:
            print(f"Matched GitHub URL: {r.get('url')} path={r.get('path')}")
            return r

    # 5) path_prefix で1件だけならそれ
    if len(candidates) == 1:
        print(f"Using sole repo candidate: {candidates[0].get('path')}")
        return candidates[0]

    raise RuntimeError(
        "repo not found for path="
        f"{path} (normalized={want}). "
        f"candidates={json.dumps(candidates, ensure_ascii=False)[:3000]}"
    )


def pull_once(host: str, token: str, path: str, repo_id_env: str = "") -> dict:
    repo = resolve_repo(host, token, path, repo_id_env)
    repo_id = int(repo["id"])
    print(f"Resolved repo_id={repo_id} path={repo.get('path')}")
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
    path = os.environ.get("DATABRICKS_REPO_PATH", "").strip()
    repo_id_env = os.environ.get("DATABRICKS_REPO_ID", "").strip()
    if not host or not token or (not path and not repo_id_env):
        print("DATABRICKS_HOST / TOKEN and REPO_PATH (or REPO_ID) required", file=sys.stderr)
        return 2

    print(f"Pulling Git folder (configured path): {path or '(by REPO_ID)'}")
    max_attempts = int(os.environ.get("DATABRICKS_PULL_RETRIES", "4"))
    for attempt in range(1, max_attempts + 1):
        print(f"=== Git folder pull attempt {attempt}/{max_attempts} ===")
        try:
            pull_once(host, token, path, repo_id_env)
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
