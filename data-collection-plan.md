# データ取得 実行計画・詳細TODO

対象リポジトリ: [kpop_agent_power_data](https://github.com/riverstone0228-dx/kpop_agent_power_data)
関連: [kpop-power-index.md](kpop-power-index.md) / [data-sources.md](data-sources.md) / [data-model.md](data-model.md)

## 全体方針

```
GitHub Actions (日次cron JST 6:00)
 ├─ ① アーティスト日次スナップショット (YouTube + Wikipedia) → data/raw/
 ├─ ② Apple / LINE / スペースシャワー チャート → data/*_charts/
 ├─ ③ mine_chart_ids.py → scripts/artist_external_ids.csv 更新
 ├─ ④ OTHER TOP15 リバランス → data/other_agency_top15/
 └─ ⑤ git commit & push (リポジトリの data/ が原本)
      └─ (Phase 4) Databricks Delta にも書き込み
```

v1データソース: **YouTube / Wikipedia / Apple / LINE / Space Shower**  
Spotifyは不使用 ([spotify-api-change-2026.md](spotify-api-change-2026.md))。

## リポジトリ構成

```
kpop_agent_power_data/
├── .github/workflows/daily_collect.yml
├── scripts/
│   ├── artist_master.csv / other_agency_master.csv / master_data.py
│   ├── artist_external_ids.csv / track_external_ids.csv / external_ids.py
│   ├── fetch_youtube.py / fetch_wikipedia.py / run_daily.py
│   ├── fetch_apple_charts.py / fetch_line_charts.py / fetch_spaceshower_charts.py
│   ├── mine_chart_ids.py / resolve_artist_ids.py / resolve_apple_artist_ids.py
│   └── requirements.txt
├── data/raw/
├── data/apple_charts/ / data/line_charts/ / data/spaceshower_charts/
├── data/other_agency_top15/
└── README.md
```

## 次のアクション (GitHub本稼働)

1. このワークスペースの内容を `kpop_agent_power_data` に push
2. GitHub Secrets に `YOUTUBE_API_KEY` のみ登録
3. Actions → Daily K-pop Data Collection → Run workflow (手動テスト)
4. `data/` にCSVがコミットされることを確認 → cron本稼働

## 決定事項サマリ

| 項目 | 方針 |
|---|---|
| データソース | YouTube / Wikipedia / Apple / LINE / Space Shower |
| OTHERプール | 20〜30組目標。集計はTOP15 (チャート勢い+YouTube+ヒステリシス) |
| 楽曲マスタ | タイトル曲のみ。YouTube TOP10 + チャート出現曲で初期選定 |
| 保存先 | GitHubリポジトリの `data/` (CSV)。DatabricksはPhase 4 |
| 実行タイミング | 毎日 JST 6:00 |
