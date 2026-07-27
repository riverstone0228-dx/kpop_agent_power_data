# Databricks Free Edition — K-POP データ自動反映ガイド

関連: [data-model.md](../data-model.md) · [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

## 仕組み

```text
GitHub Actions (毎日 JST 6:00)
  → data/*.csv を収集・commit・push
  → Databricks Git folder を Pull（最新 main）
  → Databricks Job を起動
      → Git folder 内の data/ と scripts/ を読む
      → Delta tables に MERGE
```

Volume は使いません。正本は GitHub、Databricks は Git folder 経由で同期します。

## セットアップ手順

### 1. スキーマ作成

Databricks → **SQL Editor** で [`01_ddl.sql`](01_ddl.sql) を実行。

| 名前 | 役割 |
|------|------|
| `workspace.kpop_bronze` | 統合テーブル（日別CSVを1つに） |
| `workspace.kpop_gold` | 7日差分などの VIEW |

### 2. Git folder を接続

1. Databricks → **Workspace** → **Create → Git folder**
2. URL: `https://github.com/riverstone0228-dx/kpop_agent_power_data`
3. Branch: `main`
4. `databricks/02_load.py` が見えることを確認

Git folder のフルパスをメモ（例）:

```text
/Workspace/Users/riverstone0228@gmail.com/kpop_agent_power_data
```

パスは Git folder を右クリック → **Copy path** / ブラウザURLから確認できます。

### 3. Job を作成（Workspace ソース）

1. **Workflows → Jobs → Create Job**
2. Task type: **Notebook**
3. Source: **Workspace**（Git provider ではない）
4. Path: Browse で Git folder 内の `databricks/02_load.py` を選択
5. Compute: **Serverless**
6. Save → **Job ID** をメモ（URL の `/jobs/数字`）

### 4. Databricks PAT を発行

1. 左下ユーザーアイコン → **Settings**
2. **Developer** → **Access tokens** → **Generate new token**
3. トークンをコピー（再表示不可）

### 5. GitHub Secrets を登録

GitHub リポジトリ → **Settings → Secrets and variables → Actions → New repository secret**

| Secret名 | 値の例 / 取り方 |
|-----------|----------------|
| `DATABRICKS_HOST` | `https://dbc-xxxx.cloud.databricks.com`（末尾スラッシュなし） |
| `DATABRICKS_TOKEN` | 手順4の PAT |
| `DATABRICKS_JOB_ID` | 手順3の Job ID（数字のみ） |
| `DATABRICKS_REPO_PATH` | 手順2の Git folder フルパス |

既存の `YOUTUBE_API_KEY` / `SLACK_WEBHOOK_URL` はそのまま残します。

### 6. 疎通テスト

1. GitHub → **Actions** → **Daily K-pop Data Collection** → **Run workflow**
2. ログで確認:
   - `Pull Databricks Git folder` 成功
   - `Trigger Databricks bronze load job` 成功
3. Databricks Job Runs に新しい実行があること
4. SQL で件数確認:

```sql
SELECT date, COUNT(*) AS n
FROM workspace.kpop_bronze.fact_artist_daily
GROUP BY date
ORDER BY date DESC;
```

### 7. Gold VIEW

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

Databricks で Git folder を **Pull** してから `02_load.py` → **Run All** でも OK。  
`MERGE` なので同じ日付は上書きされ、二重化しません。

## 次のステップ

1. Space Shower / OTHER TOP15 も同様に fact 化
2. Pages レポートを Databricks SQL から読む
3. Databricks AI で「今日のサマリー」→ Slack
