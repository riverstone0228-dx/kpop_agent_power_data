# Databricks Free Edition — K-POP データ格納ガイド

関連: [data-model.md](../data-model.md) · [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)

## なぜ Volume 経由か

Free Edition は **outbound インターネットが制限**されています。GitHub から直接 `curl` / `spark.read.csv("https://...")` が失敗することがあるため、最初は次の流れが確実です。

```text
ローカル / GitHub の CSV
    ↓ (ブラウザで Upload)
Volume: /Volumes/workspace/kpop_bronze/landing/...
    ↓ (このリポジトリの Notebook)
Delta tables in workspace.kpop_bronze.*
    ↓
Views in workspace.kpop_gold.*
```

GitHub Actions からの自動書き込みは、接続が安定してから Phase 2 でよいです。

## 30分でやる手順

### 1. スキーマ作成

Databricks → **SQL Editor** で [`01_ddl.sql`](01_ddl.sql) を実行。

できるもの:

| 名前 | 役割 |
|------|------|
| `workspace.kpop_bronze` | 統合テーブル（日別CSVを1つに） |
| `workspace.kpop_gold` | 7日差分などの VIEW |

※ カタログは Free Edition 既定の **`workspace`** を使います。独自 catalog も作れますが、権限トラブルを避けるためまずこれで十分です。

### 2. Volume を作る

1. Catalog → `workspace` → `kpop_bronze`
2. **Create Volume** → 名前 `landing`（managed でOK）
3. 次のフォルダ構成で Upload（ローカルから）:

```text
landing/
  raw/                 ← data/raw/*.csv
  apple_charts/        ← data/apple_charts/YYYY-MM-DD.csv（summary除外）
  line_charts/
  youtube_videos/
  song_rankings/       ← top_*.csv / hot_*.csv
  masters/
    artist_master.csv
    other_agency_master.csv
    track_master.csv
```

### 3. ロード Notebook

1. Repo の [`02_load_from_volume.py`](02_load_from_volume.py) を Databricks にインポート  
   （または内容を新規 Notebook に貼り付け）
2. **Serverless** で Run All
3. セル末尾の件数表示を確認

再実行しても `MERGE` なので同じ日付は上書きされ、二重化しません。

### 4. Gold VIEW

[`03_gold_views.sql`](03_gold_views.sql) を実行。

例:

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

## 運用リズム（推奨）

| 頻度 | 作業 |
|------|------|
| 毎日 | GitHub Actions が CSV を更新（現状どおり） |
| 週1〜毎日手動 | Volume に差分 Upload → Notebook Run All |
| 後で自動化 | Databricks Job + Git folder / Token（Free Edition の制限を見て判断） |

## 次のステップ（余裕ができたら）

1. Space Shower / OTHER TOP15 も同様に fact 化  
2. Pages レポートを Databricks SQL から読む（または gold を CSV export）  
3. Databricks AI で「今日のサマリー」→ Slack  

まずは **`fact_artist_daily` が日付横断で SELECT できる**ところまで行けば、Phase 4 の第一関門クリアです。
