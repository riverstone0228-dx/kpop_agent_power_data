# Databricks notebook source
# MAGIC %md
# MAGIC # RIVERSTONE K-POP — Free Edition ローダー
# MAGIC
# MAGIC ## 前提
# MAGIC 1. `01_ddl.sql` を実行済み
# MAGIC 2. Volume に CSV を置いている（下記パス）
# MAGIC
# MAGIC ```
# MAGIC /Volumes/workspace/kpop_bronze/landing/
# MAGIC   raw/YYYY-MM-DD.csv
# MAGIC   apple_charts/YYYY-MM-DD.csv
# MAGIC   line_charts/YYYY-MM-DD.csv
# MAGIC   youtube_videos/YYYY-MM-DD.csv
# MAGIC   song_rankings/top_YYYY-MM-DD.csv
# MAGIC   song_rankings/hot_YYYY-MM-DD.csv
# MAGIC   masters/artist_master.csv
# MAGIC   masters/other_agency_master.csv
# MAGIC   masters/track_master.csv
# MAGIC ```
# MAGIC
# MAGIC Free Edition は outbound が制限されるため、**GitHub から直接 curl せず Volume 経由**が安全です。
# MAGIC ローカルの `data/` と `scripts/*_master.csv` をまとめてアップロードしてください。

# COMMAND ----------

from pyspark.sql import functions as F
from datetime import datetime, timezone

LANDING = "/Volumes/workspace/kpop_bronze/landing"
LOADED_AT = datetime.now(timezone.utc).isoformat()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ヘルパー

# COMMAND ----------

def read_csv_glob(path_glob: str):
    return (
        spark.read
        .option("header", True)
        .option("multiLine", True)
        .option("escape", '"')
        .csv(path_glob)
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

artist_paths = [
    f"{LANDING}/masters/artist_master.csv",
    f"{LANDING}/masters/other_agency_master.csv",
]

dfs = []
for p, src in [
    (f"{LANDING}/masters/artist_master.csv", "artist_master.csv"),
    (f"{LANDING}/masters/other_agency_master.csv", "other_agency_master.csv"),
]:
    try:
        d = read_csv_glob(p).withColumn("source_file", F.lit(src))
        dfs.append(d)
        print(f"loaded {src}: {d.count()} rows")
    except Exception as e:
        print(f"skip {src}: {e}")

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_track（フルリフレッシュ）

# COMMAND ----------

try:
    tracks = (
        read_csv_glob(f"{LANDING}/masters/track_master.csv")
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    (
        tracks.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable("workspace.kpop_bronze.dim_track")
    )
    print(f"dim_track overwrite done: {tracks.count()}")
except Exception as e:
    print(f"skip dim_track: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_artist_daily（日付パーティション MERGE）

# COMMAND ----------

raw = (
    read_csv_glob(f"{LANDING}/raw/*.csv")
    .withColumn("date", to_date("date"))
    .withColumn("youtube_subscribers", to_bigint("youtube_subscribers"))
    .withColumn("youtube_total_views", to_bigint("youtube_total_views"))
    .withColumn("youtube_video_count", to_bigint("youtube_video_count"))
    .withColumn("wikipedia_pv_ja", to_bigint("wikipedia_pv_ja"))
    .withColumn("wikipedia_pv_en", to_bigint("wikipedia_pv_en"))
    .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
)

# 欠けている列があっても進める
for c in ["youtube_channel_thumbnail"]:
    if c not in raw.columns:
        raw = raw.withColumn(c, F.lit(None).cast("string"))

raw.createOrReplaceTempView("stg_artist_daily")

spark.sql(
    """
    MERGE INTO workspace.kpop_bronze.fact_artist_daily t
    USING stg_artist_daily s
    ON t.date = s.date AND t.agency = s.agency AND t.artist_name = s.artist_name
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """
)
print("fact_artist_daily merge done:", raw.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_line_chart_daily

# COMMAND ----------

try:
    line = (
        read_csv_glob(f"{LANDING}/line_charts/[0-9]*.csv")
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
    spark.sql(
        """
        MERGE INTO workspace.kpop_bronze.fact_line_chart_daily t
        USING stg_line s
        ON t.date = s.date AND t.rank = s.rank AND t.line_track_id = s.line_track_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
    print("fact_line_chart_daily merge done:", line.count())
except Exception as e:
    print("skip line:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_apple_chart_daily

# COMMAND ----------

try:
    apple = (
        read_csv_glob(f"{LANDING}/apple_charts/[0-9]*.csv")
        .withColumn("date", to_date("date"))
        .withColumn("rank", to_int("rank"))
        .withColumn("loaded_at", F.lit(LOADED_AT).cast("timestamp"))
    )
    if "artwork_url" not in apple.columns:
        apple = apple.withColumn("artwork_url", F.lit(None).cast("string"))
    apple.createOrReplaceTempView("stg_apple")
    spark.sql(
        """
        MERGE INTO workspace.kpop_bronze.fact_apple_chart_daily t
        USING stg_apple s
        ON t.date = s.date AND t.country = s.country AND t.rank = s.rank
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
    print("fact_apple_chart_daily merge done:", apple.count())
except Exception as e:
    print("skip apple:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_youtube_video_daily

# COMMAND ----------

try:
    yt = (
        read_csv_glob(f"{LANDING}/youtube_videos/[0-9]*.csv")
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
    spark.sql(
        """
        MERGE INTO workspace.kpop_bronze.fact_youtube_video_daily t
        USING stg_yt s
        ON t.date = s.date AND t.video_id = s.video_id AND t.selection = s.selection
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
    print("fact_youtube_video_daily merge done:", yt.count())
except Exception as e:
    print("skip youtube:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_song_rank_daily (top + hot)

# COMMAND ----------

rank_frames = []
for pattern, rank_type in [
    (f"{LANDING}/song_rankings/top_*.csv", "top"),
    (f"{LANDING}/song_rankings/hot_*.csv", "hot"),
]:
    try:
        d = read_csv_glob(pattern)
        # ファイル名から日付を取るのが難しい場合、CSVに date が無ければパス解析が必要。
        # top_YYYY-MM-DD.csv / hot_YYYY-MM-DD.csv を前提に input_file_name を使う。
        d = (
            d.withColumn("_file", F.input_file_name())
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
        # hot は chart_delta、top は chart_points
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
    except Exception as e:
        print(f"skip {rank_type}: {e}")

if rank_frames:
    ranks = rank_frames[0]
    for d in rank_frames[1:]:
        ranks = ranks.unionByName(d, allowMissingColumns=True)
    ranks.createOrReplaceTempView("stg_ranks")
    spark.sql(
        """
        MERGE INTO workspace.kpop_bronze.fact_song_rank_daily t
        USING stg_ranks s
        ON t.date = s.date AND t.rank_type = s.rank_type AND t.rank = s.rank
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
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
        print(f"{t}: ERR {e}")
