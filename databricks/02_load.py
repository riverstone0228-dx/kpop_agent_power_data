# Databricks notebook source
# MAGIC %md
# MAGIC # RIVERSTONE K-POP — Git folder ローダー
# MAGIC
# MAGIC ## 前提
# MAGIC 1. `01_ddl.sql` を実行済み
# MAGIC 2. Databricks の **Git folder** でこのリポジトリを接続済み
# MAGIC
# MAGIC ## 仕組み
# MAGIC - Git folder 内の `data/` と `scripts/` を直接読む
# MAGIC - Volume は不要（Volume の作成・アップロードも不要）
# MAGIC - GitHub Actions が毎日 push → Databricks Job がこの Notebook を実行
# MAGIC - 無いフォルダは静かにスキップ

# COMMAND ----------

import os
from pyspark.sql import functions as F
from datetime import datetime, timezone

LOADED_AT = datetime.now(timezone.utc).isoformat()

# Git folder のルート（Notebook からの相対パス）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in dir() else "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).rsplit("/databricks", 1)[0]

DATA_DIR = os.path.join(REPO_ROOT, "data")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

print(f"REPO_ROOT = {REPO_ROOT}")
print(f"DATA_DIR  = {DATA_DIR}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ヘルパー

# COMMAND ----------

def dir_exists(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except Exception:
        return False


def file_exists(path: str) -> bool:
    try:
        return os.path.isfile(path)
    except Exception:
        return False


def list_csv(dir_path: str, prefix: str = "") -> list[str]:
    if not dir_exists(dir_path):
        return []
    return sorted([
        os.path.join(dir_path, f)
        for f in os.listdir(dir_path)
        if f.endswith(".csv") and f.startswith(prefix)
    ])


def read_csv(paths: list[str]):
    if not paths:
        return None
    return (
        spark.read
        .option("header", True)
        .option("multiLine", True)
        .option("escape", '"')
        .csv(paths)
    )


def to_bigint(col):
    return F.when(F.col(col).isNull() | (F.col(col) == ""), F.lit(None)).otherwise(
        F.col(col).cast("bigint")
    )


def to_double(col):
    return F.when(F.col(col).isNull() | (F.col(col) == ""), F.lit(None)).otherwise(
        F.col(col).cast("double")
    )


def to_int(col):
    return F.when(F.col(col).isNull() | (F.col(col) == ""), F.lit(None)).otherwise(
        F.col(col).cast("int")
    )


def to_date(col):
    return F.to_date(F.col(col))

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_artist（フルリフレッシュ）

# COMMAND ----------

dfs = []
for src in ["artist_master.csv", "other_agency_master.csv"]:
    p = os.path.join(SCRIPTS_DIR, src)
    if not file_exists(p):
        print(f"skip {src}: not found")
        continue
    d = read_csv([p]).withColumn("source_file", F.lit(src))
    dfs.append(d)
    print(f"loaded {src}: {d.count()} rows")

if dfs:
    dim = dfs[0]
    for d in dfs[1:]:
        dim = dim.unionByName(d, allowMissingColumns=True)
    dim = dim.withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    (
        dim.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable("workspace.kpop_bronze.dim_artist")
    )
    print("dim_artist overwrite done")
else:
    print("skip dim_artist: no master files")

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_track（フルリフレッシュ）

# COMMAND ----------

track_path = os.path.join(SCRIPTS_DIR, "track_master.csv")
if file_exists(track_path):
    tracks = (
        read_csv([track_path])
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    (
        tracks.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable("workspace.kpop_bronze.dim_track")
    )
    print(f"dim_track overwrite done: {tracks.count()}")
else:
    print("skip dim_track: track_master.csv not found")

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_artist_daily（MERGE）

# COMMAND ----------

raw_dir = os.path.join(DATA_DIR, "raw")
raw_files = list_csv(raw_dir)
if not raw_files:
    raise FileNotFoundError(f"必須: {raw_dir}/*.csv がありません。")

raw = (
    read_csv(raw_files)
    .withColumn("date", to_date("date"))
    .withColumn("youtube_subscribers", to_bigint("youtube_subscribers"))
    .withColumn("youtube_total_views", to_bigint("youtube_total_views"))
    .withColumn("youtube_video_count", to_bigint("youtube_video_count"))
    .withColumn("wikipedia_pv_ja", to_bigint("wikipedia_pv_ja"))
    .withColumn("wikipedia_pv_en", to_bigint("wikipedia_pv_en"))
    .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
)

for c in ["youtube_channel_thumbnail"]:
    if c not in raw.columns:
        raw = raw.withColumn(c, F.lit(None).cast("string"))

raw.createOrReplaceTempView("stg_artist_daily")

spark.sql("""
    MERGE INTO workspace.kpop_bronze.fact_artist_daily t
    USING stg_artist_daily s
    ON t.date = s.date AND t.agency = s.agency AND t.artist_name = s.artist_name
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
print("fact_artist_daily merge done:", raw.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_line_chart_daily（任意）

# COMMAND ----------

line_dir = os.path.join(DATA_DIR, "line_charts")
line_files = [f for f in list_csv(line_dir) if os.path.basename(f)[:1].isdigit()]
if not line_files:
    print("skip line: not found")
else:
    line = (
        read_csv(line_files)
        .withColumn("date", to_date("date"))
        .withColumn("chart_date", to_date("chart_date"))
        .withColumn("rank", to_int("rank"))
        .withColumn("rank_variation", to_int("rank_variation"))
        .withColumn("score", to_double("score"))
        .withColumn("listened_count", to_bigint("listened_count"))
        .withColumn("like_count", to_bigint("like_count"))
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    for c in ["artist_image_url", "album_image_url"]:
        if c not in line.columns:
            line = line.withColumn(c, F.lit(None).cast("string"))
    line.createOrReplaceTempView("stg_line")
    spark.sql("""
        MERGE INTO workspace.kpop_bronze.fact_line_chart_daily t
        USING stg_line s
        ON t.date = s.date AND t.rank = s.rank AND t.line_track_id = s.line_track_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("fact_line_chart_daily merge done:", line.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_apple_chart_daily（任意）

# COMMAND ----------

apple_dir = os.path.join(DATA_DIR, "apple_charts")
apple_files = [f for f in list_csv(apple_dir) if os.path.basename(f)[:1].isdigit()]
if not apple_files:
    print("skip apple: not found")
else:
    apple = (
        read_csv(apple_files)
        .withColumn("date", to_date("date"))
        .withColumn("rank", to_int("rank"))
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    if "artwork_url" not in apple.columns:
        apple = apple.withColumn("artwork_url", F.lit(None).cast("string"))
    apple.createOrReplaceTempView("stg_apple")
    spark.sql("""
        MERGE INTO workspace.kpop_bronze.fact_apple_chart_daily t
        USING stg_apple s
        ON t.date = s.date AND t.country = s.country AND t.rank = s.rank
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("fact_apple_chart_daily merge done:", apple.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_youtube_video_daily（任意）

# COMMAND ----------

yt_dir = os.path.join(DATA_DIR, "youtube_videos")
yt_files = [f for f in list_csv(yt_dir) if os.path.basename(f)[:1].isdigit()]
if not yt_files:
    print("skip youtube: not found")
else:
    yt = (
        read_csv(yt_files)
        .withColumn("date", to_date("date"))
        .withColumn("rank", to_int("rank"))
        .withColumn("view_count", to_bigint("view_count"))
        .withColumn("like_count", to_bigint("like_count"))
        .withColumn("comment_count", to_bigint("comment_count"))
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    if "thumbnail_url" not in yt.columns:
        yt = yt.withColumn(
            "thumbnail_url",
            F.concat(F.lit("https://i.ytimg.com/vi/"), F.col("video_id"), F.lit("/mqdefault.jpg")),
        )
    yt.createOrReplaceTempView("stg_yt")
    spark.sql("""
        MERGE INTO workspace.kpop_bronze.fact_youtube_video_daily t
        USING stg_yt s
        ON t.date = s.date AND t.video_id = s.video_id AND t.selection = s.selection
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("fact_youtube_video_daily merge done:", yt.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_song_rank_daily (top + hot)（任意）

# COMMAND ----------

rank_dir = os.path.join(DATA_DIR, "song_rankings")
rank_frames = []
for prefix, rank_type in [("top_", "top"), ("hot_", "hot")]:
    files = list_csv(rank_dir, prefix=prefix)
    if not files:
        print(f"skip {rank_type}: not found")
        continue
    d = read_csv(files)
    d = (
        d.withColumn("_file", F.col("_metadata.file_path"))
        .withColumn(
            "date",
            F.to_date(
                F.regexp_extract(F.col("_file"), r"(top|hot)_(\d{4}-\d{2}-\d{2})", 2)
            ),
        )
        .withColumn("rank_type", F.lit(rank_type))
        .withColumn("rank", to_int("rank"))
        .withColumn("score", to_double("score"))
        .withColumn("youtube_views", to_bigint("youtube_views"))
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    if "chart_points" not in d.columns:
        d = d.withColumn("chart_points", F.lit(None).cast("double"))
    else:
        d = d.withColumn("chart_points", to_double("chart_points"))
    if "chart_delta" not in d.columns:
        d = d.withColumn("chart_delta", F.lit(None).cast("double"))
    else:
        d = d.withColumn("chart_delta", to_double("chart_delta"))
    for c in [
        "agency_logo_url",
        "artist_image_url",
        "artwork_url",
        "youtube_thumbnail_url",
        "platforms",
        "youtube_video_id",
        "sub_agency",
        "track_id",
    ]:
        if c not in d.columns:
            d = d.withColumn(c, F.lit(None).cast("string"))
    rank_frames.append(d)
    print(f"loaded {rank_type}: {d.count()}")

if rank_frames:
    ranks = rank_frames[0]
    for d in rank_frames[1:]:
        ranks = ranks.unionByName(d, allowMissingColumns=True)
    ranks.createOrReplaceTempView("stg_ranks")
    spark.sql("""
        MERGE INTO workspace.kpop_bronze.fact_song_rank_daily t
        USING stg_ranks s
        ON t.date = s.date AND t.rank_type = s.rank_type AND t.rank = s.rank
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("fact_song_rank_daily merge done")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 確認

# COMMAND ----------

for t in [
    "workspace.kpop_bronze.dim_artist",
    "workspace.kpop_bronze.dim_track",
    "workspace.kpop_bronze.fact_artist_daily",
    "workspace.kpop_bronze.fact_line_chart_daily",
    "workspace.kpop_bronze.fact_apple_chart_daily",
    "workspace.kpop_bronze.fact_youtube_video_daily",
    "workspace.kpop_bronze.fact_song_rank_daily",
]:
    try:
        n = spark.table(t).count()
        print(f"{t}: {n}")
    except Exception as e:
        print(f"{t}: empty or missing")
