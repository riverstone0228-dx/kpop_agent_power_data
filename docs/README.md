# GitHub Pages — K-POP POWER REPORT

日次収集後に `scripts/build_report.py` が `docs/data/report.json` を更新します。
静的サイト本体は [`docs/index.html`](docs/index.html) です。

## 公開手順（初回のみ）

1. GitHub リポジトリ → **Settings** → **Pages**
2. **Build and deployment** → Source: **Deploy from a branch**
3. Branch: **main** / Folder: **/docs** → Save
4. 数分後、次のURLで公開されます:

`https://riverstone0228-dx.github.io/kpop_agent_power_data/`

## ローカル確認

```bash
python3 scripts/build_report.py
cd docs && python3 -m http.server 8080
# http://localhost:8080
```

## レポート内容

- 事務所パワー（YouTube登録者合計）
- アーティスト TOP10
- 楽曲 TOP10 / HOT10
- YouTube 動画 TOP10
- 事務所フィルター（HYBE / JYP / YG / SM / OTHER）で各チャート連動
