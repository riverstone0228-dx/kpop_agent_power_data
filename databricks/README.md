# Databricks Free Edition — K-POP データ自動反映ガイド

関連: [data-model.md](../data-model.md) · [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

## 仕組み

```text
GitHub Actions (毎日 JST 6:00)
  → data/*.csv を収集・commit・push
  → Databricks Job をトリガー
      → Git folder 経由で data/ と scripts/ を直接読む
      → Delta tables に MERGE
```

Volume は使いません。Git folder がリポジトリのファイルを直接見ます。

## セットアップ手順

### 1. スキーマ作成

Databricks → **SQL Editor** で [`01_ddl.sql`](01_ddl.sql) を実行。

| 名前 | 役割 |
|------|------|
| `workspace.kpop_bronze` | 統合テーブル（日別CSVを1つに） |
| `workspace.kpop_gold` | 7日差分などの VIEW |

### 2. Git folder を接続

1. Databricks → **Workspace** → 好きな場所で **Add → Git folder**
2. リポジトリURL: `https://github.com/riverstone0228-dx/kpop_agent_power_data`
3. Branch: `main`
4. 接続完了すると `databricks/02_load.py` が Notebook として見える

### 3. Job を作成

1. **Workflows → Jobs → Create Job**
2. Task: Notebook → Git folder 内の `databricks/02_load.py` を指定
3. Compute: Serverless
4. Save → Job ID をメモ

### 4. GitHub Secrets を登録

リポジトリの Settings → Secrets → Actions に以下を追加:

| Secret名 | 値 |
|-----------|------|
| `DATABRICKS_HOST` | `https://dbc-xxxx.cloud.databricks.com`（あなたのワークスペースURL） |
| `DATABRICKS_TOKEN` | Databricks PAT（User Settings → Developer → Access tokens） |
| `DATABRICKS_JOB_ID` | 手順3でメモした Job ID |

これで毎日の GitHub Actions 完了後に自動で Databricks Job が起動します。

### 5. Gold VIEW

[`03_gold_views.sql`](03_gold_views.sql) を SQL Editor で実行。

```sql
SELECT * FROM workspace.kpop_gold.v_agency_power_daily ORDER BY date DESC, youtube_subscribers DESC;
SELECT * FROM workspace.kpop_gold.v_artist_metrics_7d WHERE date = current_date();
```

※ 7日差分は、同じアーティストの行が **8日分以上**溜まってから意味が出ます。

## テーブル対応表

| Delta | 元 |
|-------|-----|
| `fact_artist_daily` | `data/raw/*.csv` |
| `fact_line_chart_daily` | `data/line_charts/*.csv` |
| `fact_apple_chart_daily` | `data/apple_charts/*.csv` |
| `fact_youtube_video_daily` | `data/youtube_videos/*.csv` |
| `fact_song_rank_daily` | `data/song_rankings/top_*.csv` + `hot_*.csv` |
| `dim_artist` / `dim_track` | `scripts/*master*.csv` |

## 手動実行

Databricks で Git folder を開き `02_load.py` → **Run All** でも OK。  
`MERGE` なので同じ日付は上書きされ、二重化しません。

## 次のステップ

1. Space Shower / OTHER TOP15 も同様に fact 化
2. Pages レポートを Databricks SQL から読む
3. Databricks AI で「今日のサマリー」→ Slack
